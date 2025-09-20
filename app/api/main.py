from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from typing import Dict, Any
import io
import pandas as pd
from app.db.duck import get_con, init_duck
from app.query.spec import QuerySpec
from app.query.planner import build_sql

app = FastAPI(title="propmetrics", version="0.1")


@app.on_event("startup")
def _startup():
    init_duck()


@app.post("/aggregate")
def aggregate(spec: QuerySpec) -> Dict[str, Any]:
    sql, params, echo = build_sql(spec)
    con = get_con()
    df: pd.DataFrame = con.execute(sql, params).df()

    # Column order: keys first (if present), then metrics
    key_cols = []
    if spec.groupby == "month":
        key_cols = ["month"]
        # stringify month to ISO date (YYYY-MM-01)
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
    return out


@app.post("/download")
def download(spec: QuerySpec):
    sql, params, _ = build_sql(spec)
    con = get_con()
    df: pd.DataFrame = con.execute(sql, params).df()
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"]).dt.strftime("%Y-%m-%d")
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="aggregate.csv"'
    })
