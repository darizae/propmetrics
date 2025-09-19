from app.etl.nyc_normalize import _colmap


def test_colmap_basic():
    cols = ["BOROUGH", "NEIGHBORHOOD", "BUILDING CLASS CATEGORY", "SALE PRICE", "GROSS SQUARE FEET", "SALE DATE"]
    mapping = _colmap(cols)
    assert set(mapping.keys()) >= {"borough", "neighborhood", "building_class_category", "sale_price",
                                   "gross_square_feet", "sale_date"}
