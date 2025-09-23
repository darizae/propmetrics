from pathlib import Path
import duckdb
from dotenv import load_dotenv
from app.core.utils import env

_con: duckdb.DuckDBPyConnection | None = None


def _connect_and_mount(parquet_path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute("PRAGMA threads=4")
    p = str(parquet_path).replace("'", "''")
    con.execute(f"CREATE OR REPLACE VIEW brw AS SELECT * FROM read_parquet('{p}')")
    con.execute("SELECT 1 FROM brw LIMIT 1")
    return con


def init_duck() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        return _con
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    parquet_path = data_dir / "parquet" / "de_boris_brw" / "de_boris_brw.parquet"
    if not parquet_path.exists():
        raise SystemExit(f"Parquet not found: {parquet_path}")
    _con = _connect_and_mount(parquet_path)
    return _con


def init_duck_with_parquet(parquet_path: Path) -> duckdb.DuckDBPyConnection:
    global _con
    if _con is not None:
        try:
            _con.close()
        except Exception:
            pass
        _con = None
    _con = _connect_and_mount(Path(parquet_path))
    return _con


def reset_duck() -> None:
    global _con
    if _con is not None:
        try:
            _con.close()
        except Exception:
            pass
        _con = None


def get_con() -> duckdb.DuckDBPyConnection:
    return init_duck()
