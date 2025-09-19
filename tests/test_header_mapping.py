from app.etl.nyc_normalize import _colmap
import json, glob
from pathlib import Path


def test_raw_metadata_exists():
    metas = glob.glob("data/raw/nyc_rolling_sales/*/*/metadata.json")
    assert len(metas) >= 5, "Expect metadata.json for all five boroughs"


def test_parquet_and_schema_exist():
    assert Path("data/parquet/nyc_rolling_sales/nyc_rolling_sales.parquet").exists()
    sj = Path("data/meta/nyc_rolling_sales/schema.json")
    assert sj.exists()
    schema = json.loads(sj.read_text())
    assert "columns" in schema and "fingerprint" in schema


def test_colmap_basic():
    cols = ["BOROUGH", "NEIGHBORHOOD", "BUILDING CLASS CATEGORY", "SALE PRICE", "GROSS SQUARE FEET", "SALE DATE"]
    mapping = _colmap(cols)
    assert mapping["BOROUGH"] == "borough"
    assert mapping["NEIGHBORHOOD"] == "neighborhood"
    assert mapping["BUILDING CLASS CATEGORY"] == "building_class_category"
    assert mapping["SALE PRICE"] == "sale_price"
    assert mapping["GROSS SQUARE FEET"] == "gross_square_feet"
    assert mapping["SALE DATE"] == "sale_date"