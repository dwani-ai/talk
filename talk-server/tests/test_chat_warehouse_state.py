from fastapi.testclient import TestClient

import main
from routers import chat as chat_router


client = TestClient(main.app)


def test_chat_returns_warehouse_state_for_warehouse_agent(monkeypatch):
    async def _fake_call_agent(agent_name, user_text, session_id, request_id=None):
        assert agent_name == "warehouse_orchestrator"
        return {
            "reply": "ugv-1 moved to [5.0, 0.0, 0.0].",
            "warehouse_state": {
                "warehouse": {"width": 50.0, "depth": 30.0, "height": 10.0},
                "robots": [{"id": "ugv-1", "type": "ugv", "position": [5.0, 0.0, 0.0]}],
                "items": [],
            },
        }

    monkeypatch.setattr(chat_router, "call_agent", _fake_call_agent)
    res = client.post(
        "/v1/chat",
        headers={"X-Session-ID": "s-test"},
        json={"text": "move ugv north", "mode": "agent", "agent_name": "warehouse_orchestrator"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "ugv-1 moved to [5.0, 0.0, 0.0]."
    assert isinstance(body.get("warehouse_state"), dict)
    assert isinstance(body["warehouse_state"].get("robots"), list)
