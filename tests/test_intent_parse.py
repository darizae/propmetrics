import json


def test_parse_monthly_since_2018(client):
    r = client.post("/intent/parse", json={"text": "Monthly NRW since 2018"})
    assert r.status_code == 200
    spec = r.json()["spec"]
    assert spec["groupby"] == "month"
    assert spec["date_range"]["start"] <= "2018-01-01"
    a = client.post("/aggregate", json=spec)
    assert a.status_code == 200
    j = a.json()
    assert "row_count" in j and isinstance(j["row_count"], int)


def test_parse_koeln_bochum_interval(client):
    r = client.post("/intent/parse", json={"text": "Köln und Bochum 2011..2024"})
    assert r.status_code == 200
    spec = r.json()["spec"]
    assert spec["groupby"] == "none"
    assert spec["date_range"]["start"] == "2011-01-01"
    assert spec["date_range"]["end"] == "2024-12-31"
    assert spec.get("municipality") and all(m in ["köln", "bochum"] for m in spec["municipality"])


def test_parse_landuse_in_2023(client):
    r = client.post("/intent/parse", json={"text": "NUTA WA, WR in 2023"})
    assert r.status_code == 200
    spec = r.json()["spec"]
    assert spec["date_range"]["start"] == "2023-01-01"
    assert spec["date_range"]["end"] == "2023-12-31"
    assert sorted(spec.get("land_use", [])) == ["WA", "WR"]
    a = client.post("/aggregate", json=spec)
    assert a.status_code == 200
