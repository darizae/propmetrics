import re, pandas as pd, os
from pathlib import Path
import duckdb


def test_parquet_coercions_invariants():
    p = Path(os.environ.get("DATA_DIR", "./data")) / "parquet" / "de_boris_brw" / "de_boris_brw.parquet"
    assert p.exists()
    df = pd.read_parquet(p)
    assert df["stichtag"].dropna().map(lambda s: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))).all()
    assert (df["eur_per_m2"] > 0).all()


def test_duckdb_median_semantics():
    con = duckdb.connect(database=":memory:")
    con.execute("create table t(x double)");
    con.execute("insert into t values (1), (null), (3)")
    m = con.execute("select median(x) from t").fetchone()[0]
    assert m == 2.0
