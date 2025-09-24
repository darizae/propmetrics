import io
import json
import os
import re
import time
import yaml
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Callable, Deque
from collections import deque, defaultdict

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Response, Request, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse

from app.api.models import AggregateResponse
from app.cache.redis_cache import get_cache, spec_cache_key
from app.core.utils import env
from app.db.duck import get_con, init_duck, reset_duck
from app.query.planner import build_sql
from app.query.spec import QuerySpec
from app.llm.intent import load_vocab, parse as parse_intent
from app.llm.agent import ask as llm_ask

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

# ------------ process state ------------

_vocab_cache: Dict[str, Any] = {}
_rate_qps = float(os.getenv("RATE_QPS", "0"))
_rate_burst = int(os.getenv("RATE_BURST", "10"))
_rl_buckets: Dict[str, Deque[float]] = defaultdict(deque)


# ------------ lifespan ------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.cache = get_cache()
    init_duck()
    # lazy vocab
    app.state.vocab_loaded = False
    yield


# ------------ app ------------

tags_metadata = [
    {"name": "analytics", "description": "Aggregates over NRW Bodenrichtwerte Parquet"},
    {"name": "ops", "description": "Operational endpoints"},
]

app = FastAPI(title="propmetrics", version="0.3", lifespan=lifespan, openapi_tags=tags_metadata)

# ------------ CORS (UI only) ------------

cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


# ------------ helpers ------------

def _require_admin(request: Request) -> None:
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="unauthorized")
    token = auth.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def _rate_limit(request: Request) -> None:
    if _rate_qps <= 0:
        return
    path = request.url.path
    if path in ("/health", "/openapi.yaml"):
        return
    # only limit /aggregate and /intent/parse and /llm/ask
    if path not in ("/aggregate", "/intent/parse", "/llm/ask"):
        return
    ip = (request.client.host if request.client else "unknown") or "unknown"
    now = time.monotonic()
    bucket = _rl_buckets[ip]
    window = 1.0
    # drop old
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    # capacity
    cap = max(_rate_burst, int(_rate_qps))
    if len(bucket) >= cap:
        raise HTTPException(status_code=429, detail="rate_limited")
    bucket.append(now)


ACTIONS_PATH = Path(__file__).resolve().parents[2] / "actions" / "openapi.yaml"


# ------------ actions export ------------

@app.get("/openapi.yaml", include_in_schema=False)
def openapi_yaml() -> Response:
    if not ACTIONS_PATH.exists():
        raw = app.openapi()
        paths = raw.get("paths", {})
        keep = {k: v for k, v in paths.items() if k in ("/aggregate", "/download")}
        raw["paths"] = keep
        raw["info"]["title"] = "propmetrics-tools"
        raw["info"]["description"] = (
            "Tool-only API for computing aggregates over NRW Bodenrichtwerte Parquet. Return numbers; no prose."
        )
        raw["servers"] = [{"url": os.getenv("SERVER_URL", "http://localhost:8000")}]
        ACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ACTIONS_PATH.write_text(yaml.safe_dump(raw, sort_keys=False))
    data = ACTIONS_PATH.read_text()
    return Response(content=data, media_type="application/yaml")


# ------------ analytics ------------

@app.post(
    "/aggregate",
    tags=["analytics"],
    response_model=AggregateResponse,
    response_model_exclude_none=True,
    summary="Compute aggregates",
    description="Count zones and median land value (€/m²) with optional grouping by month, municipality, or land_use.",
)
def aggregate(spec: QuerySpec, response: Response, request: Request) -> Dict[str, Any]:
    _rate_limit(request)
    cache = getattr(request.app.state, "cache", None)
    cache_ok = bool(cache and cache.healthy())
    if cache_ok:
        key = spec_cache_key("agg", spec)
        cached = cache.get(key)
        if cached:
            response.headers["x-cache"] = "hit"
            return json.loads(cached)

    sql, params, echo = build_sql(spec)
    con = get_con()
    df: pd.DataFrame = con.execute(sql, params).df()

    key_cols = []
    if spec.groupby == "month":
        key_cols = ["month"]
        if "month" in df.columns:
            df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m-%d")
    elif spec.groupby == "municipality":
        key_cols = ["municipality"]
    elif spec.groupby == "land_use":
        key_cols = ["land_use"]

    metric_cols = ["zones", "median_eur_per_m2"]
    cols = key_cols + metric_cols
    df = df[cols] if set(cols).issubset(df.columns) else df

    if not df.empty:
        df = df.astype(object).where(pd.notna(df), None)

    data = df.to_dict(orient="records")
    out = {"filters_echo": echo, "row_count": len(data), "data": data}

    if cache_ok:
        cache.set(key, json.dumps(out).encode("utf-8"))
        response.headers["x-cache"] = "miss"
    else:
        response.headers["x-cache"] = "bypass"
    return out


@app.post(
    "/download",
    tags=["analytics"],
    summary="Download aggregate as CSV",
    description="Identical result set as /aggregate returned as CSV.",
)
def download(spec: QuerySpec, request: Request):
    cache = getattr(request.app.state, "cache", None)
    cache_ok = bool(cache and cache.healthy())
    key = spec_cache_key("csv", spec) if cache_ok else None

    if cache_ok:
        cached = cache.get(key)
        if cached:
            resp = StreamingResponse(iter([cached]), media_type="text/csv")
            resp.headers["Content-Disposition"] = 'attachment; filename="aggregate.csv"'
            resp.headers["x-cache"] = "hit"
            return resp

    sql, params, _ = build_sql(spec)
    con = get_con()
    df = con.execute(sql, params).df()
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    resp = StreamingResponse(iter([csv_bytes]), media_type="text/csv")
    resp.headers["Content-Disposition"] = 'attachment; filename="aggregate.csv"'
    if cache_ok:
        cache.set(key, csv_bytes)
        resp.headers["x-cache"] = "miss"
    else:
        resp.headers["x-cache"] = "bypass"
    return resp


# ------------ ops ------------

@app.get(
    "/health",
    tags=["ops"],
    summary="Service health",
    description="Snapshot timestamps, row count, schema fingerprint, and cache status.",
)
def health(request: Request) -> Dict[str, Any]:
    data_dir = Path(env("DATA_DIR"))
    meta_dir = data_dir / "meta" / "de_boris_brw"
    schema_fp = None
    if (meta_dir / "schema.json").exists():
        sj = json.loads((meta_dir / "schema.json").read_text())
        schema_fp = sj.get("fingerprint")

    summary = {}
    summary_path = data_dir / "parquet" / "de_boris_brw" / "SUMMARY.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())

    raw_root = data_dir / "raw" / "de_boris_brw"
    snapshots = {}
    if raw_root.exists():
        snaps = sorted([p for p in raw_root.iterdir() if p.is_dir()], reverse=True)
        latest = snaps[0].name if snaps else None
        fetched_at = None
        if snaps and (snaps[0] / "metadata.json").exists():
            md = json.loads((snaps[0] / "metadata.json").read_text())
            fetched_at = md.get("fetched_at_utc")
        snapshots = {"latest_snapshot": latest, "fetched_at_utc": fetched_at}

    cache = getattr(request.app.state, "cache", None)
    enabled = bool(cache and cache.client is not None)
    healthy = bool(cache and cache.healthy())
    return {
        "status": "ok",
        "dataset": "de_boris_brw",
        "schema_fingerprint": schema_fp,
        "rows": summary.get("rows"),
        "cache": {"enabled": enabled, "healthy": healthy},
        "snapshots": snapshots,
    }


@app.post(
    "/admin/refresh",
    tags=["ops"],
    summary="Admin refresh (token-gated)",
    description="Clears cache keys and remounts DuckDB over Parquet. Requires Authorization: Bearer <ADMIN_TOKEN>.",
)
def admin_refresh(request: Request) -> Dict[str, Any]:
    _require_admin(request)
    cache = getattr(request.app.state, "cache", None)
    cleared = 0
    cache_enabled = bool(cache and cache.client is not None)
    cache_healthy = bool(cache and cache.healthy())
    if cache_enabled and cache_healthy:
        try:
            for k in cache.client.scan_iter(match="pm:v1:*", count=1000):
                cache.client.delete(k)
                cleared += 1
        except Exception:
            cleared = 0
    reset_duck()
    init_duck()
    return {
        "status": "ok",
        "cache": {"enabled": cache_enabled, "healthy": cache_healthy, "cleared": cleared},
        "duckdb": "reloaded",
    }


# ------------ intent parser (not exported in Actions) ------------

@app.post("/intent/parse", tags=["ops"], summary="Parse free text to QuerySpec")
def intent_parse(payload: Dict[str, str] = Body(...), request: Request = None) -> Dict[str, Any]:
    _rate_limit(request)
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, detail={"code": "PARSE_ERROR", "detail": "empty"})
    # lazy load vocab per-process
    if not getattr(app.state, "vocab_loaded", False):
        _v = load_vocab(get_con())
        _vocab_cache["vocab"] = _v
        app.state.vocab_loaded = True
    spec = parse_intent(text, _vocab_cache["vocab"])
    return {"spec": spec, "tokens": {"len": len(text)}}


# ------------ UI ------------

_HTML = """<!doctype html><html><head>
<meta charset="utf-8"><title>propmetrics UI</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Helvetica,Arial,sans-serif;margin:2rem;max-width:900px}
input,button{font-size:1rem;padding:.6rem .8rem}
table{border-collapse:collapse;margin-top:1rem;width:100%}
th,td{border:1px solid #ddd;padding:.5rem;text-align:left}
code{background:#f6f8fa;padding:2px 4px;border-radius:4px}
</style></head><body>
<h1>propmetrics</h1>
<form id="qform">
<input id="q" type="text" placeholder="e.g., Monthly since 2018; Köln und Bochum 2011..2024" size="60"/>
<button type="submit">Run</button>
<label><input type="checkbox" id="use_llm"> via GPT-3.5</label>
</form>
<pre id="echo"></pre>
<div id="result"></div>
<script>
const form=document.getElementById('qform');
const echo=document.getElementById('echo');
const res=document.getElementById('result');
const useLLM=document.getElementById('use_llm');
form.addEventListener('submit', async (e)=>{
  e.preventDefault(); res.innerHTML=''; echo.textContent='';
  const text=document.getElementById('q').value||'';
  try{
    if(useLLM.checked){
      const lr=await fetch('/llm/ask',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text})});
      if(!lr.ok){res.textContent='LLM error '+lr.status;return;}
      const body=await lr.json();
      echo.textContent=JSON.stringify(body.filters_echo||{},null,2);
      renderTable(body.data||[], body.row_count||0);
    }else{
      const pr=await fetch('/intent/parse',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text})});
      const p=await pr.json(); echo.textContent=JSON.stringify(p.spec,null,2);
      const ar=await fetch('/aggregate',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(p.spec)});
      const body=await ar.json(); renderTable(body.data||[], body.row_count||0);
    }
  }catch(err){res.textContent='Error';}
});
function renderTable(rows, count){
  if(!rows.length){res.innerHTML='<p>No rows</p>';return;}
  const cols=[...new Set(rows.flatMap(r=>Object.keys(r)))];
  const th=cols.map(c=>'<th>'+c+'</th>').join('');
  const trs=rows.map(r=>'<tr>'+cols.map(c=>'<td>'+ (r[c] ?? '') +'</td>').join('')+'</tr>').join('');
  res.innerHTML='<p>Rows: '+count+'</p><table><thead><tr>'+th+'</tr></thead><tbody>'+trs+'</tbody></table>';
}
</script></body></html>"""


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui():
    return HTMLResponse(_HTML)


# ------------ LLM front (not exported in Actions) ------------

@app.post("/llm/ask", tags=["ops"], summary="LLM front to tools (numbers-only)")
def llm_ask_handler(payload: Dict[str, str] = Body(...), request: Request = None) -> JSONResponse:
    _rate_limit(request)
    text = (payload.get("text") or "").strip()
    out = llm_ask(text)
    return JSONResponse(out)
