import asyncio
import logging
import os
import sys
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Ensure we can import the travel-planner agent module
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TRAVEL_AGENT_DIR = os.path.join(CURRENT_DIR, "travel-planner-sub-agents")
if TRAVEL_AGENT_DIR not in sys.path:
    sys.path.append(TRAVEL_AGENT_DIR)

try:
    from agent import root_agent  # type: ignore
except Exception as exc:  # pragma: no cover - import-time failure logging
    raise RuntimeError(f"Failed to import travel planner agent: {exc}") from exc


logger = logging.getLogger("agents_service")
logging.basicConfig(level=logging.INFO)


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier from Talk (X-Session-ID).")
    message: str = Field(..., description="User's latest utterance (already transcribed).")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent's reply text.")
    state: Dict[str, Any] | None = Field(
        default=None,
        description="Optional debug snapshot of agent state for this session.",
    )


APP_NAME = os.getenv("AGENTS_APP_NAME", "talk_travel_planner")

_session_service = InMemorySessionService()
_known_sessions: set[str] = set()

_agents: Dict[str, Runner] = {
    # Root ADK multi-agent for travel planning.
    "travel_planner": Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    ),
}


app = FastAPI(
    title="Talk Agents Service",
    description="HTTP wrapper around Google ADK agents for the Talk system.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


def _ensure_session(user_id: str, session_id: str) -> None:
    """Create an ADK session if it does not already exist.

    InMemorySessionService.create_session is async in this ADK version, so we
    run it in a fresh event loop from this sync context.
    """
    key = f"{user_id}:{session_id}"
    if key in _known_sessions:
        return
    asyncio.run(
        _session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
    )
    _known_sessions.add(key)


def _run_agent_message(runner: Runner, user_id: str, session_id: str, message: str) -> ChatResponse:
    _ensure_session(user_id=user_id, session_id=session_id)

    content = types.Content(role="user", parts=[types.Part(text=message)])
    events = runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    )

    final_text_parts: list[str] = []
    last_state: Dict[str, Any] | None = None

    for event in events:
        if getattr(event, "is_final_response", None) and event.is_final_response() and event.content:
            for p in event.content.parts:
                text = getattr(p, "text", None)
                if text:
                    final_text_parts.append(str(text))
        # Some runners expose session state snapshots on events; capture if present.
        state = getattr(event, "state", None)
        if isinstance(state, dict):
            last_state = state

    if not final_text_parts:
        raise HTTPException(status_code=502, detail="Agent returned empty response")

    reply_text = " ".join(" ".join(final_text_parts).split())
    return ChatResponse(reply=reply_text, state=last_state)


@app.post("/v1/agents/{agent_name}/chat", response_model=ChatResponse)
def chat(agent_name: str, body: ChatRequest) -> ChatResponse:
    runner = _agents.get(agent_name)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{agent_name}'")

    session_id = body.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        # Use the external session_id as both user_id and session_id for simplicity.
        return _run_agent_message(runner, user_id=session_id, session_id=session_id, message=message)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive error handling
        logger.exception("Agent call failed")
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}") from exc


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port)

