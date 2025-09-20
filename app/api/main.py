from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from typing import Dict, Any
from pathlib import Path
import io, json
import pandas as pd

from app.db.duck import get_con, init_duck
from app.query.spec import QuerySpec
from app.query.planner import build_sql
from app.cache.redis_cache import get_cache, spec_cache_key
from app.core.utils import env
from dotenv import load_dotenv

cache = get_cache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_duck()
    yield


app = FastAPI(title="propmetrics", version="0.1", lifespan=lifespan)


@app.post("/aggregate")
def aggregate(spec: QuerySpec, response: Response) -> Dict[str, Any]:
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

    data = df.to_dict(orient="records")
    out = {
        "filters_echo": echo,
        "row_count": len(data),
        "data": data,
        "notes": "metrics computed in DuckDB; medians ignore NULLs"
    }
    cache.set(key, json.dumps(out).encode("utf-8"))
    response.headers["x-cache"] = "miss"
    return out


@app.post("/download")
def download(spec: QuerySpec, response: Response):
    key = spec_cache_key("csv", spec)
    cached = cache.get(key)
    if cached:
        response.headers["x-cache"] = "hit"
        return StreamingResponse(iter([cached]), media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="aggregate.csv"'})

    sql, params, _ = build_sql(spec)
    con = get_con()
    df: pd.DataFrame = con.execute(sql, params).df()
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")
    cache.set(key, csv_bytes)
    response.headers["x-cache"] = "miss"
    return StreamingResponse(iter([csv_bytes]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="aggregate.csv"'})


@app.get("/health")
def health() -> Dict[str, Any]:
    load_dotenv()
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

    return {
        "status": "ok",
        "dataset": "nyc_rolling_sales",
        "schema_fingerprint": schema_fp,
        "rows": summary.get("rows"),
        "cache": {
            "enabled": cache.client is not None,
            "healthy": cache.healthy()
        },
        "boroughs": boroughs
    }
