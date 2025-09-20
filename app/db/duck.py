from pathlib import Path
import duckdb
from dotenv import load_dotenv
from app.core.utils import env

_con: duckdb.DuckDBPyConnection | None = None


def init_duck() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        return _con

    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    parquet_path = data_dir / "parquet" / "nyc_rolling_sales" / "nyc_rolling_sales.parquet"
    if not parquet_path.exists():
        raise SystemExit(f"Parquet not found: {parquet_path}")

    con = duckdb.connect(database=":memory:")
    con.execute("PRAGMA threads=4")

    p = str(parquet_path).replace("'", "''")
    con.execute(f"CREATE OR REPLACE VIEW nyc AS SELECT * FROM read_parquet('{p}')")

    _con = con
    return _con


def get_con() -> duckdb.DuckDBPyConnection:
    return init_duck()
