import asyncio
import logging
import os
import sys
from importlib import util as importlib_util
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from warehouse.state_store import get_state as get_warehouse_state_snapshot
from warehouse.commands import execute_warehouse_command, verify_warehouse_state_after_command
from warehouse.direct_commands import parse_direct_warehouse_command

# Ensure we can import the travel-planner and viva-examiner agent modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

TRAVEL_AGENT_DIR = os.path.join(CURRENT_DIR, "travel-planner-sub-agents")
if TRAVEL_AGENT_DIR not in sys.path:
    sys.path.append(TRAVEL_AGENT_DIR)

try:
    from agent import root_agent  # type: ignore
except Exception as exc:  # pragma: no cover - import-time failure logging
    raise RuntimeError(f"Failed to import travel planner agent: {exc}") from exc


VIVA_AGENT_DIR = os.path.join(CURRENT_DIR, "viva-examiner")
VIVA_AGENT_PATH = os.path.join(VIVA_AGENT_DIR, "agent.py")

try:
    viva_spec = importlib_util.spec_from_file_location("viva_examiner_agent", VIVA_AGENT_PATH)
    if viva_spec is None or viva_spec.loader is None:
        raise RuntimeError("Could not load spec for viva examiner agent")
    viva_module = importlib_util.module_from_spec(viva_spec)
    viva_spec.loader.exec_module(viva_module)  # type: ignore[attr-defined]
    viva_root_agent = getattr(viva_module, "root_viva_agent")
except Exception as exc:  # pragma: no cover - import-time failure logging
    raise RuntimeError(f"Failed to import viva examiner agent: {exc}") from exc


FIX_MY_CITY_AGENT_DIR = os.path.join(CURRENT_DIR, "fix-my-city")
FIX_MY_CITY_AGENT_PATH = os.path.join(FIX_MY_CITY_AGENT_DIR, "agent.py")

try:
    fix_my_city_spec = importlib_util.spec_from_file_location(
        "fix_my_city_agent", FIX_MY_CITY_AGENT_PATH
    )
    if fix_my_city_spec is None or fix_my_city_spec.loader is None:
        raise RuntimeError("Could not load spec for fix-my-city agent")
    fix_my_city_module = importlib_util.module_from_spec(fix_my_city_spec)
    fix_my_city_spec.loader.exec_module(fix_my_city_module)  # type: ignore[attr-defined]
    root_fix_my_city_agent = getattr(fix_my_city_module, "root_fix_my_city_agent")
except Exception as exc:  # pragma: no cover - import-time failure logging
    raise RuntimeError(f"Failed to import fix-my-city agent: {exc}") from exc


ORCHESTRATOR_AGENT_DIR = os.path.join(CURRENT_DIR, "orchestrator")
ORCHESTRATOR_AGENT_PATH = os.path.join(ORCHESTRATOR_AGENT_DIR, "agent.py")

try:
    orchestrator_spec = importlib_util.spec_from_file_location(
        "orchestrator_agent", ORCHESTRATOR_AGENT_PATH
    )
    if orchestrator_spec is None or orchestrator_spec.loader is None:
        raise RuntimeError("Could not load spec for orchestrator agent")
    orchestrator_module = importlib_util.module_from_spec(orchestrator_spec)
    orchestrator_spec.loader.exec_module(orchestrator_module)  # type: ignore[attr-defined]
    root_orchestrator_agent = getattr(orchestrator_module, "root_orchestrator_agent")
except Exception as exc:  # pragma: no cover - import-time failure logging
    raise RuntimeError(f"Failed to import orchestrator agent: {exc}") from exc


WAREHOUSE_AGENT_DIR = os.path.join(CURRENT_DIR, "warehouse")
WAREHOUSE_AGENT_PATH = os.path.join(WAREHOUSE_AGENT_DIR, "orchestrator_agent.py")

try:
    warehouse_spec = importlib_util.spec_from_file_location(
        "warehouse_orchestrator_agent", WAREHOUSE_AGENT_PATH
    )
    if warehouse_spec is None or warehouse_spec.loader is None:
        raise RuntimeError("Could not load spec for warehouse orchestrator agent")
    warehouse_module = importlib_util.module_from_spec(warehouse_spec)
    warehouse_spec.loader.exec_module(warehouse_module)  # type: ignore[attr-defined]
    root_warehouse_orchestrator_agent = getattr(
        warehouse_module, "root_warehouse_orchestrator_agent"
    )
except Exception as exc:  # pragma: no cover - import-time failure logging
    raise RuntimeError(f"Failed to import warehouse orchestrator agent: {exc}") from exc


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
    warehouse_state: Dict[str, Any] | None = Field(
        default=None,
        description="Verified warehouse state (robots, items, warehouse) when agent is warehouse_orchestrator; use to update 3D view.",
    )


class WarehouseCommandRequest(BaseModel):
    robot: str = Field(..., description="Robot to control: 'uav', 'ugv', or 'arm'.")
    action: str | None = Field(
        default=None,
        description="Action: 'move', 'pick', 'drop', 'pick_from_stack', 'place_on_stack'.",
    )
    direction: str | None = Field(
        default=None,
        description="Optional direction: 'north', 'south', 'east', or 'west'.",
    )
    item_id: str | None = Field(default=None, description="Item ID for pick/drop/place_on_stack.")
    stack_id: str | None = Field(default=None, description="Stack ID for pick_from_stack or place_on_stack.")
    x: float | None = Field(
        default=None,
        description="Optional absolute X coordinate.",
    )
    y: float | None = Field(
        default=None,
        description="Optional absolute Y coordinate.",
    )
    z: float | None = Field(
        default=None,
        description="Optional absolute Z coordinate.",
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
    # Viva/voce examiner agent.
    "viva_examiner": Runner(
        agent=viva_root_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    ),
    # Fix-my-city complaint registration and status agent.
    "fix_my_city": Runner(
        agent=root_fix_my_city_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    ),
    # Orchestrator agent that routes to travel_planner, viva_examiner, or fix_my_city.
    "orchestrator": Runner(
        agent=root_orchestrator_agent,
        app_name=APP_NAME,
        session_service=_session_service,
    ),
    # Warehouse orchestrator for UAV, UGV, and arm robots.
    "warehouse_orchestrator": Runner(
        agent=root_warehouse_orchestrator_agent,
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


@app.get("/v1/warehouse/state")
def get_warehouse_state() -> Dict[str, Any]:
    """Return the current warehouse robots/items state for visualization."""
    snapshot = get_warehouse_state_snapshot()
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=500, detail="Invalid warehouse state")
    return snapshot


@app.post("/v1/warehouse/command")
def warehouse_command(cmd: WarehouseCommandRequest) -> Dict[str, Any]:
    """Deterministic warehouse command. Used by API and by agents via execute_warehouse_command."""
    try:
        return execute_warehouse_command(
            robot=cmd.robot,
            action=cmd.action or "move",
            direction=cmd.direction,
            item_id=cmd.item_id,
            stack_id=cmd.stack_id,
            x=cmd.x,
            y=cmd.y,
            z=cmd.z,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


def _run_agent_message(runner: Runner, user_id: str, session_id: str, message: str, agent_name: str = "") -> ChatResponse:
    _ensure_session(user_id=user_id, session_id=session_id)
    state_before = get_warehouse_state_snapshot() if agent_name == "warehouse_orchestrator" else None

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
    warehouse_state = None
    if agent_name == "warehouse_orchestrator":
        warehouse_state = get_warehouse_state_snapshot()
        if not isinstance(warehouse_state, dict):
            warehouse_state = None
        # Validate agent result against actual state for direct command-like requests.
        cmd = parse_direct_warehouse_command(message)
        if cmd and isinstance(state_before, dict) and isinstance(warehouse_state, dict):
            ok, reason = verify_warehouse_state_after_command(
                cmd["robot"],
                cmd.get("action", "move"),
                warehouse_state,
                prev_state=state_before,
                direction=cmd.get("direction"),
                item_id=cmd.get("item_id"),
                stack_id=cmd.get("stack_id"),
                x=cmd.get("x"),
                y=cmd.get("y"),
                z=cmd.get("z"),
            )
            if not ok:
                # Self-heal: if agent response wasn't reflected in state, execute the
                # same parsed direct command deterministically and return real state.
                try:
                    det = execute_warehouse_command(
                        robot=cmd["robot"],
                        action=cmd.get("action", "move"),
                        direction=cmd.get("direction"),
                        item_id=cmd.get("item_id"),
                        stack_id=cmd.get("stack_id"),
                        x=cmd.get("x"),
                        y=cmd.get("y"),
                        z=cmd.get("z"),
                    )
                    warehouse_state = get_warehouse_state_snapshot()
                    if not isinstance(warehouse_state, dict):
                        warehouse_state = {
                            "warehouse": {},
                            "robots": det.get("robots", []),
                            "items": det.get("items", []),
                        }
                    reply_text = str(det.get("reply") or "").strip() or "Command completed."
                except ValueError:
                    reply_text = (
                        f"Command not verified against warehouse state: {reason}. "
                        "No confirmed state change was applied."
                    )
    return ChatResponse(reply=reply_text, state=last_state, warehouse_state=warehouse_state)


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
        return _run_agent_message(runner, user_id=session_id, session_id=session_id, message=message, agent_name=agent_name)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive error handling
        logger.exception("Agent call failed")
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}") from exc


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.getenv("PORT", "8081"))
    uvicorn.run(app, host="0.0.0.0", port=port)

