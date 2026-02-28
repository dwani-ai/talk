from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_chat_rejects_invalid_agent_name():
    res = client.post(
        "/v1/chat",
        json={"text": "hello", "mode": "agent", "agent_name": "unknown_agent"},
    )
    assert res.status_code == 422


def test_chat_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setenv("DWANI_API_KEY", "test-key")
    res = client.post("/v1/chat", json={"text": "hello", "mode": "llm"})
    assert res.status_code == 401


def test_chat_accepts_valid_api_key_header(monkeypatch):
    monkeypatch.setenv("DWANI_API_KEY", "test-key")
    res = client.post(
        "/v1/chat",
        headers={"X-API-Key": "test-key"},
        json={"text": "hello", "mode": "llm"},
    )
    # We only verify auth gate is passed; downstream may still fail without mock env.
    assert res.status_code != 401


def test_metrics_endpoint_exists():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text or "http_request_duration_seconds" in res.text
