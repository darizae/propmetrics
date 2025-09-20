import re


def _iso_ymd(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def test_cache_hit_header_for_aggregate(client):
    spec = {"date_range": {"start": "1991-01-01", "end": "2031-12-31"}, "groupby": "none"}
    r1 = client.post("/aggregate", json=spec)
    assert r1.status_code == 200
    assert r1.headers.get("x-cache") == "miss"
    r2 = client.post("/aggregate", json=spec)
    assert r2.status_code == 200
    assert r2.headers.get("x-cache") == "hit"
    assert r2.json() == r1.json()


def test_cache_hit_header_for_download(client):
    spec = {"date_range": {"start": "1992-01-01", "end": "2032-12-31"}, "groupby": "month"}
    r1 = client.post("/download", json=spec)
    assert r1.status_code == 200
    assert r1.headers.get("x-cache") == "miss"
    r2 = client.post("/download", json=spec)
    assert r2.status_code == 200
    assert r2.headers.get("x-cache") == "hit"


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ok"
    assert "schema_fingerprint" in payload
    assert "rows" in payload
    assert "cache" in payload and "enabled" in payload["cache"]
    b = payload.get("boroughs", {})
    for k in ["manhattan", "brooklyn", "queens", "bronx", "staten_island"]:
        if k in b:
            v = b[k]
            assert "latest_snapshot" in v


def test_cache_key_canonicalization_borough_case_and_order(client):
    spec1 = {"date_range": {"start": "1990-01-01", "end": "2030-12-31"},
             "borough": ["Manhattan", "Queens"], "groupby": "none"}
    r1 = client.post("/aggregate", json=spec1)
    assert r1.status_code == 200
    assert r1.headers.get("x-cache") == "miss"

    spec2 = {"date_range": {"start": "1990-01-01", "end": "2030-12-31"},
             "borough": ["queens", "manhattan"], "groupby": "none"}
    r2 = client.post("/aggregate", json=spec2)
    assert r2.status_code == 200
    assert r2.headers.get("x-cache") == "hit"


def test_cache_key_canonicalization_neighborhood_case_and_order(client):
    spec1 = {"date_range": {"start": "1990-01-01", "end": "2030-12-31"},
             "neighborhood": ["Chelsea", "harlem"], "groupby": "none"}
    r1 = client.post("/aggregate", json=spec1)
    assert r1.headers.get("x-cache") == "miss"

    spec2 = {"date_range": {"start": "1990-01-01", "end": "2030-12-31"},
             "neighborhood": ["HARLEM", "chelsea"], "groupby": "none"}
    r2 = client.post("/aggregate", json=spec2)
    assert r2.headers.get("x-cache") == "hit"


def test_cache_bypass_header_when_cache_unavailable(client, monkeypatch):
    # Force cache off
    from app.api import main
    main.app.state.cache = None
    spec = {"date_range": {"start": "1990-01-01", "end": "2030-12-31"}, "groupby": "none"}
    r = client.post("/aggregate", json=spec)
    assert r.status_code == 200
    assert r.headers.get("x-cache") == "bypass"
