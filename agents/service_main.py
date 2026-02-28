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

from warehouse.state_store import (
    get_state as get_warehouse_state_snapshot,
    get_warehouse_bounds,
    is_within_bounds,
    update_robot_position,
    update_robot_status,
    upsert_item,
)

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


def _get_robot_position(state: Dict[str, Any], robot_id: str) -> tuple[float, float, float]:
    robots = state.get("robots", [])
    r = next((x for x in robots if x.get("id") == robot_id), None) or {}
    pos = r.get("position") or [0.0, 0.0, 0.0]
    return float(pos[0]), float(pos[1]), float(pos[2])


def _get_item_position(state: Dict[str, Any], item_id: str) -> tuple[float, float, float] | None:
    items = state.get("items", [])
    it = next((x for x in items if x.get("id") == item_id), None)
    if not it:
        return None
    pos = it.get("position") or [0.0, 0.0, 0.0]
    return float(pos[0]), float(pos[1]), float(pos[2])


def _stack_height(state: Dict[str, Any], stack_id: str) -> int:
    items = state.get("items", [])
    return sum(1 for it in items if it.get("stack_id") == stack_id)


def _get_robot_carried_item(state: Dict[str, Any], robot_id: str) -> str | None:
    """Return item_id if robot is carrying/holding an item, else None."""
    robots = state.get("robots", [])
    r = next((x for x in robots if x.get("id") == robot_id), None) or {}
    task = r.get("current_task") or ""
    if task.startswith("carrying_"):
        return task.replace("carrying_", "").strip()
    if task.startswith("holding_"):
        return task.replace("holding_", "").strip()
    return None


def _get_robot_holding_item(state: Dict[str, Any], item_id: str) -> str | None:
    """Return robot_id if any robot is carrying/holding this item, else None."""
    for r in state.get("robots", []):
        task = r.get("current_task") or ""
        carried = None
        if task.startswith("carrying_"):
            carried = task.replace("carrying_", "").strip()
        elif task.startswith("holding_"):
            carried = task.replace("holding_", "").strip()
        if carried == item_id:
            return r.get("id")
    return None


def _get_stack_base_position(state: Dict[str, Any], stack_id: str) -> tuple[float, float]:
    """Return (x, z) base position for a stack. Uses first item or default for empty stack."""
    items = state.get("items", [])
    stack_items = [it for it in items if it.get("stack_id") == stack_id]
    if stack_items:
        pos = stack_items[0].get("position") or [25.0, 0.0, 10.0]
        return float(pos[0]), float(pos[2])
    return 25.0, 10.0


@app.post("/v1/warehouse/command")
def warehouse_command(cmd: WarehouseCommandRequest) -> Dict[str, Any]:
    """Deterministic warehouse command endpoint used by the UI.

    This bypasses the LLM and directly updates the shared warehouse state,
    so the 3D view always reflects the true robot positions.
    """
    robot_key = cmd.robot.strip().lower()
    id_map = {"uav": "uav-1", "ugv": "ugv-1", "arm": "arm-1"}
    robot_id = id_map.get(robot_key)
    if not robot_id:
        raise HTTPException(status_code=400, detail="robot must be one of: uav, ugv, arm")

    state = get_warehouse_state_snapshot()
    cx, cy, cz = _get_robot_position(state, robot_id)
    reply: str

    action = (cmd.action or "").strip().lower() or "move"

    # --- UGV pick: UGV must move to item first, then pick ---
    if action == "pick":
        if robot_key != "ugv":
            raise HTTPException(status_code=400, detail="Only UGV can pick items from the floor.")
        if not cmd.item_id:
            raise HTTPException(status_code=400, detail="item_id required for pick.")
        carried = _get_robot_carried_item(state, robot_id)
        if carried:
            raise HTTPException(
                status_code=400,
                detail=f"UGV is already carrying '{carried}'. Drop it first before picking another item.",
            )
        item_id = cmd.item_id.strip()
        items = state.get("items", [])
        item = next((it for it in items if it.get("id") == item_id), None)
        if not item:
            raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found.")
        if item.get("stack_id"):
            raise HTTPException(status_code=400, detail=f"Item '{item_id}' is on a stack. Use arm pick from stack.")
        held_by = _get_robot_holding_item(state, item_id)
        if held_by and held_by != robot_id:
            raise HTTPException(
                status_code=400,
                detail=f"Item '{item_id}' is already held by {held_by}. It must be released first.",
            )
        ix, iy, iz = _get_item_position(state, item_id) or (0.0, 0.0, 0.0)
        # 1. Move UGV to item location
        update_robot_position(robot_id, ix, 0.0, iz)
        # 2. Pick: item attaches to UGV (same position)
        upsert_item(item_id, (ix, 0.0, iz), stack_id=None)
        update_robot_status(robot_id, "working", current_task=f"carrying_{item_id}")
        reply = f"{robot_id} moved to [{ix}, 0, {iz}], picked {item_id}."

    # --- UGV drop: UGV must move to drop location first, then drop ---
    elif action == "drop":
        if robot_key != "ugv":
            raise HTTPException(status_code=400, detail="Only UGV can drop items.")
        if not cmd.item_id:
            raise HTTPException(status_code=400, detail="item_id required for drop.")
        if cmd.x is None or cmd.z is None:
            raise HTTPException(status_code=400, detail="x and z required for drop.")
        carried = _get_robot_carried_item(state, robot_id)
        item_id = cmd.item_id.strip()
        if carried != item_id:
            raise HTTPException(
                status_code=400,
                detail=f"UGV is not carrying '{item_id}'." + (f" (Currently carrying '{carried}')" if carried else ""),
            )
        tx, tz = float(cmd.x), float(cmd.z)
        if not is_within_bounds(tx, 0.0, tz):
            w, d, _ = get_warehouse_bounds()
            raise HTTPException(
                status_code=400,
                detail=f"Drop position ({tx}, {tz}) is outside warehouse bounds (0–{w} x 0–{d}).",
            )
        # 1. Move UGV to drop location
        update_robot_position(robot_id, tx, 0.0, tz)
        # 2. Drop: item placed at UGV position
        upsert_item(item_id, (tx, 0.0, tz), stack_id=None)
        update_robot_status(robot_id, "idle", current_task=None)
        reply = f"{robot_id} moved to [{tx}, 0, {tz}], dropped {item_id}."

    # --- Arm pick_from_stack: arm must move to stack top first, then pick ---
    elif action == "pick_from_stack":
        if robot_key != "arm":
            raise HTTPException(status_code=400, detail="Only arm can pick from stack.")
        if not cmd.stack_id:
            raise HTTPException(status_code=400, detail="stack_id required for pick_from_stack.")
        holding = _get_robot_carried_item(state, robot_id)
        if holding:
            raise HTTPException(
                status_code=400,
                detail=f"Arm is already holding '{holding}'. Place it on a stack first before picking another.",
            )
        stack_id = cmd.stack_id.strip()
        items = state.get("items", [])
        stack_items = [it for it in items if it.get("stack_id") == stack_id]
        if not stack_items:
            raise HTTPException(status_code=404, detail=f"No items in stack '{stack_id}'.")
        top = stack_items[-1]
        item_id = str(top.get("id"))
        ix, iy, iz = top.get("position") or [25.0, 0.0, 10.0]
        ix, iy, iz = float(ix), float(iy), float(iz)
        # 1. Move arm to stack top (item location)
        update_robot_position(robot_id, ix, iy, iz)
        # 2. Pick: item attaches to arm (same position)
        upsert_item(item_id, (ix, iy, iz), stack_id=None)
        update_robot_status(robot_id, "working", current_task=f"holding_{item_id}")
        reply = f"{robot_id} moved to [{ix}, {iy}, {iz}], picked {item_id} from {stack_id}."

    # --- Arm place_on_stack: arm must move to place height first, then place ---
    elif action == "place_on_stack":
        if robot_key != "arm":
            raise HTTPException(status_code=400, detail="Only arm can place on stack.")
        if not cmd.stack_id or not cmd.item_id:
            raise HTTPException(status_code=400, detail="stack_id and item_id required for place_on_stack.")
        holding = _get_robot_carried_item(state, robot_id)
        item_id = cmd.item_id.strip()
        if holding != item_id:
            raise HTTPException(
                status_code=400,
                detail=f"Arm is not holding '{item_id}'." + (f" (Currently holding '{holding}')" if holding else ""),
            )
        stack_id = cmd.stack_id.strip()
        level = _stack_height(state, stack_id)
        base_x, base_z = _get_stack_base_position(state, stack_id)
        y = 0.5 * (level + 1)
        if not is_within_bounds(base_x, y, base_z):
            w, d, h = get_warehouse_bounds()
            raise HTTPException(
                status_code=400,
                detail=f"Stack position ({base_x}, {y}, {base_z}) would be outside warehouse bounds.",
            )
        # 1. Move arm to place height
        update_robot_position(robot_id, base_x, y, base_z)
        # 2. Place: item on stack at arm position
        upsert_item(item_id, (base_x, y, base_z), stack_id=stack_id)
        update_robot_status(robot_id, "idle", current_task=None)
        reply = f"{robot_id} moved to [{base_x}, {y}, {base_z}], placed {item_id} on {stack_id}."

    # --- Move ---
    else:
        if cmd.x is not None and cmd.z is not None:
            tx = float(cmd.x)
            tz = float(cmd.z)
            ty = float(cmd.y) if cmd.y is not None else (0.0 if robot_key == "ugv" else 5.0)
        elif cmd.direction:
            direction = cmd.direction.strip().lower()
            step = 5.0
            dx = dz = 0.0
            if direction == "north":
                dz = -step
            elif direction == "south":
                dz = step
            elif direction == "east":
                dx = step
            elif direction == "west":
                dx = -step
            if robot_key == "uav":
                tx, ty, tz = cx + dx, 5.0, cz + dz
            elif robot_key == "ugv":
                tx, ty, tz = cx + dx, 0.0, cz + dz
            else:
                tx, ty, tz = cx + dx, cy, cz + dz
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide direction or absolute coordinates (x,y,z) for move.",
            )
        if not is_within_bounds(tx, ty, tz):
            w, d, h = get_warehouse_bounds()
            raise HTTPException(
                status_code=400,
                detail=f"Target position ({tx}, {ty}, {tz}) is outside warehouse bounds (0–{w} x 0–{d} x 0–{h}).",
            )
        updated = update_robot_position(robot_id, tx, ty, tz)
        # If robot is carrying/holding an item, move the item with it
        current = next((r for r in state.get("robots", []) if r.get("id") == robot_id), None) or {}
        task = current.get("current_task") or ""
        carried_id = None
        if task.startswith("carrying_"):
            carried_id = task.replace("carrying_", "").strip()
        elif task.startswith("holding_"):
            carried_id = task.replace("holding_", "").strip()
        if carried_id:
            if robot_key == "ugv":
                upsert_item(carried_id, (tx, 0.0, tz), stack_id=None)
            else:
                upsert_item(carried_id, (tx, ty, tz), stack_id=None)
            update_robot_status(robot_id, "working", current_task=task)
        else:
            update_robot_status(robot_id, "idle", current_task=None)
        reply = f"{robot_id} moved to [{updated['position'][0]}, {updated['position'][1]}, {updated['position'][2]}]."

    new_state = get_warehouse_state_snapshot()
    return {
        "reply": reply,
        "robots": new_state.get("robots", []),
        "items": new_state.get("items", []),
    }


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

