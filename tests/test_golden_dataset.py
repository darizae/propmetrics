from fastapi.testclient import TestClient
import pandas as pd
from app.db.duck import init_duck_with_parquet, reset_duck, init_duck


def test_golden_dataset_month_and_median(tmp_path):
    df = pd.DataFrame([
        {"municipality": "koeln", "land_use": "WA", "plz": "50667", "eur_per_m2": 1000.0, "stichtag": "2024-01-15"},
        {"municipality": "koeln", "land_use": "WA", "plz": "50667", "eur_per_m2": 2000.0, "stichtag": "2024-01-20"},
        {"municipality": "bochum", "land_use": "MI", "plz": "44787", "eur_per_m2": 3000.0, "stichtag": "2024-02-01"},
    ])
    p = tmp_path / "golden.parquet"
    df.to_parquet(p, index=False)
    reset_duck();
    init_duck_with_parquet(p)
    from app.api.main import app
    with TestClient(app) as c:
        q = {"date_range": {"start": "2024-01-01", "end": "2024-12-31"}, "groupby": "month"}
        r = c.post("/aggregate", json=q)
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 2
        jan = next(x for x in rows if x["month"] == "2024-01-01")
        feb = next(x for x in rows if x["month"] == "2024-02-01")
        assert jan["zones"] == 2
        assert jan["median_eur_per_m2"] == 1500.0
        assert feb["zones"] == 1
        assert feb["median_eur_per_m2"] == 3000.0
    reset_duck();
    init_duck()
