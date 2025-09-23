import csv, io, re


def _iso_ymd(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def test_aggregate_basic_structure(client):
    resp = client.post("/aggregate",
                       json={"date_range": {"start": "2011-01-01", "end": "2030-12-31"}, "groupby": "none"})
    assert resp.status_code == 200
    payload = resp.json()
    assert set(["filters_echo", "data", "row_count"]).issubset(payload)
    assert isinstance(payload["data"], list)
    assert payload["row_count"] in (0, 1)
    if payload["data"]:
        row = payload["data"][0]
        for k in ["zones", "median_eur_per_m2"]:
            assert k in row


def test_aggregate_groupby_month_sorting_and_format(client):
    spec = {"date_range": {"start": "2011-01-01", "end": "2030-12-31"}, "groupby": "month"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 200
    data = resp.json()["data"]
    if data:
        months = [row["month"] for row in data]
        assert all(_iso_ymd(m) for m in months)
        assert all(m.endswith("-01") for m in months)
        assert months == sorted(months)


def test_filters_echo_municipality_normalization(client):
    spec = {"date_range": {"start": "2011-01-01", "end": "2030-12-31"}, "municipality": ["Köln"], "groupby": "none"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 200
    echo = resp.json()["filters_echo"]
    assert echo["municipality"] == ["köln"]


def test_groupby_land_use_shape(client):
    spec = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "groupby": "land_use"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 200
    data = resp.json()["data"]
    if data:
        assert "land_use" in data[0]
        for row in data:
            assert "zones" in row and isinstance(row["zones"], int)


def test_download_csv_matches_json_rows_when_groupby_month(client):
    q = {"date_range": {"start": "2011-01-01", "end": "2030-12-31"}, "groupby": "month"}
    j = client.post("/aggregate", json=q).json()
    resp = client.post("/download", json=q)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    buf = io.StringIO(resp.text)
    rows = list(csv.DictReader(buf))
    assert len(rows) == j["row_count"]
    if rows:
        assert "month" in rows[0]
        assert _iso_ymd(rows[0]["month"])


def test_invalid_date_range_returns_422(client):
    spec = {"date_range": {"start": "2025-12-31", "end": "2025-01-01"}, "groupby": "none"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 422


def test_invalid_groupby_literal_returns_422(client):
    spec = {"date_range": {"start": "2011-01-01", "end": "2030-12-31"}, "groupby": "bad_choice"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 422


def test_empty_window_is_handled(client):
    spec = {"date_range": {"start": "1900-01-01", "end": "1900-12-31"}, "groupby": "none"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 200
    payload = resp.json()
    assert "row_count" in payload
    assert payload["row_count"] in (0, 1)
