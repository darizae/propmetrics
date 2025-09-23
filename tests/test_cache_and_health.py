import re


def _iso_ymd(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def test_cache_hit_header_for_aggregate(client):
    spec = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "groupby": "none"}
    r1 = client.post("/aggregate", json=spec)
    assert r1.status_code == 200 and r1.headers.get("x-cache") == "miss"
    r2 = client.post("/aggregate", json=spec)
    assert r2.status_code == 200 and r2.headers.get("x-cache") == "hit"
    assert r2.json() == r1.json()


def test_cache_hit_header_for_download(client):
    spec = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "groupby": "month"}
    r1 = client.post("/download", json=spec)
    assert r1.status_code == 200 and r1.headers.get("x-cache") == "miss"
    r2 = client.post("/download", json=spec)
    assert r2.status_code == 200 and r2.headers.get("x-cache") == "hit"


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ok"
    assert "schema_fingerprint" in payload
    assert "rows" in payload
    assert "cache" in payload and "enabled" in payload["cache"]
    s = payload.get("snapshots", {})
    if s:
        assert "latest_snapshot" in s


def test_cache_key_canonicalization_municipality_case_and_order(client):
    spec1 = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "municipality": ["Köln", "Bochum"],
             "groupby": "none"}
    r1 = client.post("/aggregate", json=spec1);
    assert r1.headers.get("x-cache") == "miss"
    spec2 = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "municipality": ["bochum", "köln"],
             "groupby": "none"}
    r2 = client.post("/aggregate", json=spec2);
    assert r2.headers.get("x-cache") == "hit"


def test_cache_bypass_header_when_cache_unavailable(client, monkeypatch):
    from app.api import main
    main.app.state.cache = None
    spec = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "groupby": "none"}
    r = client.post("/aggregate", json=spec)
    assert r.status_code == 200 and r.headers.get("x-cache") == "bypass"
