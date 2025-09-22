import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.responses import StreamingResponse

from app.api.models import AggregateResponse
from app.cache.redis_cache import get_cache, spec_cache_key
from app.core.utils import env
from app.db.duck import get_con, init_duck, reset_duck
from app.query.planner import build_sql
from app.query.spec import QuerySpec


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.cache = get_cache()
    init_duck()
    yield


tags_metadata = [
    {"name": "analytics", "description": "Aggregates over NYC rolling sales Parquet"},
    {"name": "ops", "description": "Operational endpoints"},
]

app = FastAPI(
    title="propmetrics",
    version="0.1",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
)


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


@app.post(
    "/aggregate",
    tags=["analytics"],
    response_model=AggregateResponse,
    response_model_exclude_none=True,
    summary="Compute aggregates",
    description="Compute count/sum/median metrics with optional grouping by month, neighborhood, or class.",
)
def aggregate(spec: QuerySpec, response: Response, request: Request) -> Dict[str, Any]:
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
    elif spec.groupby == "neighborhood":
        key_cols = ["neighborhood"]
    elif spec.groupby == "class":
        key_cols = ["building_class_category"]

    metric_cols = ["txns", "total_sale_price", "median_sale_price", "median_price_per_sqft"]
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
    df: pd.DataFrame = con.execute(sql, params).df()
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


@app.get(
    "/health",
    tags=["ops"],
    summary="Service health",
    description="Snapshot timestamps per borough, rows count, schema fingerprint, and cache status.",
)
def health(request: Request) -> Dict[str, Any]:
    data_dir = Path(env("DATA_DIR"))
    meta_dir = data_dir / "meta" / "nyc_rolling_sales"
    schema_fp = None
    if (meta_dir / "schema.json").exists():
        sj = json.loads((meta_dir / "schema.json").read_text())
        schema_fp = sj.get("fingerprint")

    summary = {}
    summary_path = data_dir / "parquet" / "nyc_rolling_sales" / "SUMMARY.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())

    raw_root = data_dir / "raw" / "nyc_rolling_sales"
    boroughs = {}
    if raw_root.exists():
        for bdir in sorted([p for p in raw_root.iterdir() if p.is_dir()]):
            snaps = sorted([p for p in bdir.iterdir() if p.is_dir()], reverse=True)
            latest = snaps[0].name if snaps else None
            fetched_at = None
            if snaps and (snaps[0] / "metadata.json").exists():
                md = json.loads((snaps[0] / "metadata.json").read_text())
                fetched_at = md.get("fetched_at_utc")
            boroughs[bdir.name] = {"latest_snapshot": latest, "fetched_at_utc": fetched_at}

    cache = getattr(request.app.state, "cache", None)
    enabled = bool(cache and cache.client is not None)
    healthy = bool(cache and cache.healthy())
    return {
        "status": "ok",
        "dataset": "nyc_rolling_sales",
        "schema_fingerprint": schema_fp,
        "rows": summary.get("rows"),
        "cache": {"enabled": enabled, "healthy": healthy},
        "boroughs": boroughs,
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
