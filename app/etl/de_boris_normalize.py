import json
from pathlib import Path
import duckdb
import pandas as pd
from dotenv import load_dotenv
from typer import Typer
from app.core.schema import write_schema
from app.core.utils import env, ensure_dir, dump_json

app = Typer(no_args_is_help=True)

CANON = {
    "municipality": "string",
    "land_use": "string",  # NUTA codes (e.g., WA, WR, MI, GE, W, M)
    "plz": "string",
    "eur_per_m2": "float64",  # BRW in €/m²
    "stichtag": "string",  # ISO YYYY-MM-DD
}


def _latest_snapshot_dir(raw_root: Path) -> Path:
    snaps = sorted([p for p in raw_root.iterdir() if p.is_dir()], reverse=True)
    if not snaps:
        raise SystemExit("No snapshots found for de_boris_brw")
    return snaps[0]


@app.command()
def run():
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    raw_root = data_dir / "raw" / "de_boris_brw"
    out_root = data_dir / "parquet" / "de_boris_brw"
    meta_root = data_dir

    snapdir = _latest_snapshot_dir(raw_root)
    shp_files = list(snapdir.rglob("*.shp"))
    if not shp_files:
        raise SystemExit(f"No .shp files in {snapdir}, ensure fetch step extracted the ZIP")
    shp_path = shp_files[0]

    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL spatial; LOAD spatial;")

    df = con.execute(f"""
        WITH src AS (
            SELECT
                BRW,
                STAG,
                GENA,
                ORTST,
                NUTA,
                PLZ
            FROM ST_Read('{str(shp_path).replace("'", "''")}')
        ),
        norm AS (
            SELECT
                COALESCE(
                    TRY_CAST(BRW AS DOUBLE),
                    TRY_CAST(
                        REPLACE(
                            REGEXP_REPLACE(CAST(BRW AS VARCHAR), '[\\s\\u00A0\\.]', ''),
                            ',','.'
                        ) AS DOUBLE
                    )
                ) AS eur_per_m2,
                COALESCE(
                    TRY_CAST(STAG AS DATE),
                    TRY_CAST(STRPTIME(CAST(STAG AS VARCHAR), '%Y-%m-%d') AS DATE),
                    TRY_CAST(STRPTIME(CAST(STAG AS VARCHAR), '%d.%m.%Y') AS DATE),
                    TRY_CAST(STRPTIME(CAST(STAG AS VARCHAR), '%Y%m%d') AS DATE)
                ) AS stichtag,
                CAST(GENA AS VARCHAR)        AS municipality,
                CAST(ORTST AS VARCHAR)       AS ortsteil,
                CAST(NUTA AS VARCHAR)        AS land_use,
                CAST(PLZ AS VARCHAR)         AS plz
            FROM src
        )
        SELECT
            municipality, land_use, plz, eur_per_m2, stichtag
        FROM norm
    """).df()

    # Coercions and guards in pandas (final safety net)
    df = df.dropna(subset=["eur_per_m2", "stichtag"])
    df = df[df["eur_per_m2"] > 0]
    df["stichtag"] = pd.to_datetime(df["stichtag"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["stichtag"])
    df["municipality"] = df["municipality"].fillna("")

    # Canonical selection and persist
    df = df[["municipality", "land_use", "plz", "eur_per_m2", "stichtag"]]
    ensure_dir(out_root)
    out_parquet = out_root / "de_boris_brw.parquet"
    df.to_parquet(out_parquet, index=False)

    schema = {c: str(df.dtypes[c]) for c in ["municipality", "land_use", "plz", "eur_per_m2", "stichtag"]}
    fp = write_schema(meta_root, "de_boris_brw", schema)
    summary = {"rows": int(len(df)), "columns": schema, "schema_fingerprint": fp, "output_parquet": str(out_parquet)}
    dump_json(out_root / "SUMMARY.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
