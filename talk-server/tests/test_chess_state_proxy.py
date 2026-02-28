from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url):
        assert url.endswith("/v1/chess/state")
        return _FakeResponse(
            200,
            {
                "board": {"e2": "wP"},
                "turn": "white",
                "mode": "human_vs_ai",
                "status": "in_progress",
                "move_history": [],
            },
        )


def test_chess_state_proxy(monkeypatch):
    import httpx
    monkeypatch.setenv("DWANI_AGENT_BASE_URL", "http://agents:8081")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    res = client.get("/v1/chess/state")
    assert res.status_code == 200
    body = res.json()
    assert body["turn"] == "white"
    assert isinstance(body.get("board"), dict)

