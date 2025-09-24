import os


def test_llm_mock_path(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    r = client.post("/llm/ask", json={"text": "Monthly since 2018"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("row_count"), int)
    assert "filters_echo" in body or "llm" in body
