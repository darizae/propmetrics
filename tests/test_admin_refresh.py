import os


def test_admin_refresh_unauthorized(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = client.post("/admin/refresh")
    assert r.status_code == 401


def test_admin_refresh_clears_cache_and_reloads_duck(client, monkeypatch):
    # Set token for this test
    monkeypatch.setenv("ADMIN_TOKEN", "secret123")

    # Warm cache
    spec = {"date_range": {"start": "1990-01-01", "end": "2030-12-31"}, "groupby": "none"}
    r1 = client.post("/aggregate", json=spec)
    assert r1.headers.get("x-cache") == "miss"
    r2 = client.post("/aggregate", json=spec)
    assert r2.headers.get("x-cache") == "hit"

    # Refresh
    r_admin = client.post("/admin/refresh", headers={"Authorization": "Bearer secret123"})
    assert r_admin.status_code == 200
    body = r_admin.json()
    assert body["status"] == "ok"
    assert "cache" in body and isinstance(body["cache"].get("cleared", 0), int)
    assert body.get("duckdb") == "reloaded"

    # Cache should be empty for this key again
    r3 = client.post("/aggregate", json=spec)
    assert r3.headers.get("x-cache") == "miss"
