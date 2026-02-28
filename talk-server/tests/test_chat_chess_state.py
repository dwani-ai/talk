from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_chat_returns_chess_state_for_chess_agent(monkeypatch):
    async def _fake_call_agent(agent_name, user_text, session_id):
        assert agent_name == "chess_orchestrator"
        return {
            "reply": "wP moved e2->e4. black to move.",
            "chess_state": {
                "board": {"e4": "wP"},
                "turn": "black",
                "mode": "human_vs_ai",
                "status": "in_progress",
                "move_history": [{"from": "e2", "to": "e4", "piece": "wP"}],
            },
        }

    monkeypatch.setattr(main, "call_agent", _fake_call_agent)
    res = client.post(
        "/v1/chat",
        headers={"X-Session-ID": "s-test-chess"},
        json={"text": "e2 to e4", "mode": "agent", "agent_name": "chess_orchestrator"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "wP moved e2->e4. black to move."
    assert isinstance(body.get("chess_state"), dict)
    assert body["chess_state"]["turn"] == "black"

