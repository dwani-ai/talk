from fastapi.testclient import TestClient

import service_main


client = TestClient(service_main.app)


class _FakePart:
    def __init__(self, text: str):
        self.text = text


class _FakeContent:
    def __init__(self, text: str):
        self.parts = [_FakePart(text)]


class _FakeEvent:
    def __init__(self, text: str):
        self.content = _FakeContent(text)

    def is_final_response(self):
        return True


class _FakeRunner:
    def run(self, user_id, session_id, new_message):
        return [_FakeEvent("hello from fake agent")]


def test_healthz():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_agent_chat(monkeypatch):
    monkeypatch.setattr(service_main, "_ensure_session", lambda user_id, session_id: None)
    monkeypatch.setitem(service_main._agents, "travel_planner", _FakeRunner())
    res = client.post(
        "/v1/agents/travel_planner/chat",
        json={"session_id": "session-1", "message": "hi"},
    )
    assert res.status_code == 200
    assert res.json()["reply"] == "hello from fake agent"
