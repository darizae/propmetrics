from fastapi.testclient import TestClient
import pandas as pd
from app.db.duck import init_duck_with_parquet, reset_duck, init_duck


def test_golden_dataset_month_and_medians(tmp_path):
    df = pd.DataFrame([
        {"borough": "manhattan", "neighborhood": "X", "building_class_category": "A", "sale_price": 1000.0,
         "gross_square_feet": 100.0, "sale_date": "2024-01-15", "price_per_sqft": 10.0},
        {"borough": "manhattan", "neighborhood": "X", "building_class_category": "A", "sale_price": 2000.0,
         "gross_square_feet": 200.0, "sale_date": "2024-01-20", "price_per_sqft": 10.0},
        {"borough": "manhattan", "neighborhood": "Y", "building_class_category": "B", "sale_price": 3000.0,
         "gross_square_feet": 100.0, "sale_date": "2024-02-01", "price_per_sqft": 30.0},
    ])
    p = tmp_path / "golden.parquet"
    df.to_parquet(p, index=False)

    reset_duck()
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
        assert jan["txns"] == 2
        assert jan["total_sale_price"] == 3000.0
        assert jan["median_sale_price"] == 1500.0
        assert jan["median_price_per_sqft"] == 10.0
        assert feb["txns"] == 1
        assert feb["median_price_per_sqft"] == 30.0

    reset_duck()
    init_duck()
