from datetime import date
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)


def _base_spec():
    return {
        "date_range": {"start": "1990-01-01", "end": "2030-12-31"},
        "groupby": "none"
    }


def test_aggregate_basic():
    resp = client.post("/aggregate", json=_base_spec())
    assert resp.status_code == 200
    payload = resp.json()
    assert "filters_echo" in payload and "data" in payload and "row_count" in payload
    assert isinstance(payload["data"], list)


def test_aggregate_groupby_month():
    spec = _base_spec() | {"groupby": "month"}
    resp = client.post("/aggregate", json=spec)
    assert resp.status_code == 200
    data = resp.json()["data"]
    if data:
        assert "month" in data[0]


def test_download_csv():
    resp = client.post("/download", json=_base_spec())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
