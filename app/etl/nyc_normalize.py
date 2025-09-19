import json
from pathlib import Path
from typing import Dict

import pandas as pd
from dotenv import load_dotenv
from typer import Typer

from app.core.schema import write_schema
from app.core.utils import env, ensure_dir, snake, dump_json

app = Typer(no_args_is_help=True)

CANON = {
    "borough": "string",
    "neighborhood": "string",
    "building_class_category": "string",
    "sale_price": "float64",
    "gross_square_feet": "float64",
    "sale_date": "string",  # ISO YYYY-MM-DD
    "price_per_sqft": "float64"
}

HEADER_ALIASES = {
    "borough": {"borough"},
    "neighborhood": {"neighborhood", "neighbourhood"},
    "building_class_category": {"building_class_category", "buildingclasscategory"},
    "sale_price": {"sale_price", "saleprice", "sale_price__", "sale_price_$"},
    "gross_square_feet": {"gross_square_feet", "gross_sq_ft", "grosssquarefeet", "gross sq ft"},
    "sale_date": {"sale_date", "saledate", "sale_date_"},
}


def _latest_snapshot_dir(raw_root: Path, borough: str) -> Path:
    bdir = raw_root / borough
    snaps = sorted([p for p in bdir.iterdir() if p.is_dir()], reverse=True)
    if not snaps:
        raise SystemExit(f"No snapshots for {borough}")
    return snaps[0]


def _read_any(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return pd.read_excel(path, dtype=str, engine="openpyxl")
    if ext == ".xls":
        return pd.read_excel(path, dtype=str, engine="xlrd")
    if ext == ".csv":
        return pd.read_csv(path, dtype=str)
    raise SystemExit(f"Unsupported extension: {ext}")


def _colmap(df_cols: list[str]) -> Dict[str, str]:
    norm = {snake(c): c for c in df_cols}
    mapping: Dict[str, str] = {}
    for canon, aliases in HEADER_ALIASES.items():
        for k, orig in norm.items():
            if k == canon or k in aliases:
                mapping[canon] = orig
                break
    missing = [c for c in CANON.keys() if c not in mapping and c != "price_per_sqft"]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")
    return mapping


@app.command()
def run():
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    raw_root = data_dir / "raw" / "nyc_rolling_sales"
    out_root = data_dir / "parquet" / "nyc_rolling_sales"
    meta_root = data_dir

    all_boroughs = [p.name for p in raw_root.iterdir() if p.is_dir()]
    frames = []

    for b in sorted(all_boroughs):
        snapdir = _latest_snapshot_dir(raw_root, b)
        files = [p for p in snapdir.iterdir() if p.is_file() and p.suffix.lower() in {".xls", ".xlsx", ".csv"}]
        if not files:
            raise SystemExit(f"No data files in {snapdir}")
        path = files[0]
        df = _read_any(path)

        colmap = _colmap(list(df.columns))
        df = df.rename(columns=colmap)

        for col in CANON.keys():
            if col not in df.columns and col != "price_per_sqft":
                df[col] = pd.NA

        # Coercions
        df["sale_price"] = pd.to_numeric(df["sale_price"].str.replace(r"[^\d.]", "", regex=True), errors="coerce")
        df["gross_square_feet"] = pd.to_numeric(df["gross_square_feet"].str.replace(r"[^\d.]", "", regex=True),
                                                errors="coerce")
        # Dates to YYYY-MM-DD
        df["sale_date"] = pd.to_datetime(df["sale_date"], errors="coerce").dt.strftime("%Y-%m-%d")

        # Drop invalids
        df = df[df["sale_price"].fillna(0) > 0]
        df.loc[df["gross_square_feet"].fillna(0) <= 0, "gross_square_feet"] = pd.NA

        # price_per_sqft
        df["price_per_sqft"] = df["sale_price"] / df["gross_square_feet"]
        df.loc[df["price_per_sqft"] == float("inf"), "price_per_sqft"] = pd.NA

        # Canon types
        df = df[["borough", "neighborhood", "building_class_category", "sale_price", "gross_square_feet", "sale_date",
                 "price_per_sqft"]]
        df["borough"] = b  # enforce
        frames.append(df)

    full = pd.concat(frames, ignore_index=True)

    # Write Parquet partitioned by sale_year and borough
    full["sale_year"] = full["sale_date"].str.slice(0, 4)
    out = out_root
    ensure_dir(out)
    full.to_parquet(out / "nyc_rolling_sales.parquet", index=False)  # monolith file for v0.1 local dev

    # Schema JSON + fingerprint
    schema = {c: str(full.dtypes[c]) for c in
              ["borough", "neighborhood", "building_class_category", "sale_price", "gross_square_feet", "sale_date",
               "price_per_sqft"]}
    fp = write_schema(meta_root, "nyc_rolling_sales", schema)

    summary = {
        "rows": int(len(full)),
        "columns": schema,
        "schema_fingerprint": fp,
        "output_parquet": str(out / "nyc_rolling_sales.parquet")
    }
    dump_json(out_root / "SUMMARY.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
