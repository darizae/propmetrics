import re
import duckdb
import pandas as pd
from pathlib import Path
import os


def test_parquet_coercions_invariants():
    p = Path(os.environ.get("DATA_DIR", "./data")) / "parquet" / "nyc_rolling_sales" / "nyc_rolling_sales.parquet"
    assert p.exists()
    df = pd.read_parquet(p)
    assert df["sale_date"].dropna().map(lambda s: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))).all()
    assert (df["sale_price"] > 0).all()
    mask = df["gross_square_feet"].isna() | (df["gross_square_feet"] <= 0)
    assert df.loc[mask, "price_per_sqft"].isna().all()


def test_duckdb_median_semantics():
    con = duckdb.connect(database=":memory:")
    con.execute("create table t(x double)")
    con.execute("insert into t values (1), (null), (3)")
    m = con.execute("select median(x) from t").fetchone()[0]
    assert m == 2.0
