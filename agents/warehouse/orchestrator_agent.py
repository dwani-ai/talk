import asyncio
import logging
import os
import sys
from importlib import util as importlib_util
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

_WAREHOUSE_DIR = os.path.dirname(os.path.abspath(__file__))
if _WAREHOUSE_DIR not in sys.path:
  sys.path.insert(0, _WAREHOUSE_DIR)

from state_store import get_state  # type: ignore[import-not-found]
from commands import execute_warehouse_command, verify_warehouse_state_after_command  # type: ignore[import-not-found]


load_dotenv()


logger = logging.getLogger("warehouse_orchestrator_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_agent(path: str, module_name: str, attr_name: str):
    spec = importlib_util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load spec for {module_name} at {path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:  # pragma: no cover
        raise RuntimeError(f"{attr_name} not found in module {module_name}") from exc


UAV_AGENT_PATH = os.path.join(CURRENT_DIR, "uav_agent.py")
UGV_AGENT_PATH = os.path.join(CURRENT_DIR, "ugv_agent.py")
ARM_AGENT_PATH = os.path.join(CURRENT_DIR, "arm_agent.py")

uav_root_agent = _load_agent(UAV_AGENT_PATH, "warehouse_uav_agent", "root_uav_agent")
ugv_root_agent = _load_agent(UGV_AGENT_PATH, "warehouse_ugv_agent", "root_ugv_agent")
arm_root_agent = _load_agent(ARM_AGENT_PATH, "warehouse_arm_agent", "root_arm_agent")


APP_NAME = os.getenv("AGENTS_APP_NAME", "talk_warehouse")
_session_service = InMemorySessionService()
_known_sessions: set[str] = set()


uav_runner = Runner(
    agent=uav_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)
ugv_runner = Runner(
    agent=ugv_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)
arm_runner = Runner(
    agent=arm_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)


def _session_id_from_context(tool_context: ToolContext) -> str:
    return (
        getattr(tool_context, "session_id", None)
        or getattr(getattr(tool_context, "session", None), "id", None)
        or "default"
    )


async def _ensure_session_async(user_id: str, session_id: str) -> None:
    """Create an ADK session if it does not already exist for this app."""
    key = f"{user_id}:{session_id}"
    if key in _known_sessions:
        return
    await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    _known_sessions.add(key)


async def _run_subagent_message_async(runner: Runner, session_id: str, message: str) -> str:
    await _ensure_session_async(user_id=session_id, session_id=session_id)

    content = types.Content(role="user", parts=[types.Part(text=message)])
    events = runner.run_async(
        user_id=session_id,
        session_id=session_id,
        new_message=content,
    )

    final_text_parts: list[str] = []
    async for event in events:
        if getattr(event, "is_final_response", None) and event.is_final_response() and event.content:
            for p in event.content.parts:
                text = getattr(p, "text", None)
                if text:
                    final_text_parts.append(str(text))

    if not final_text_parts:
        raise RuntimeError("Sub-agent returned empty response")

    return " ".join(" ".join(final_text_parts).split())


async def call_uav(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate to UAV agent. Your reply MUST be only the returned verified_fact (or brief paraphrase); do not add outcomes."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(uav_runner, session_id, message)
    tool_context.state["active_robot"] = "uav"
    return {"success": True, "verified_fact": reply, "reply": reply, "target": "uav"}


async def call_ugv(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate to UGV agent. Your reply MUST be only the returned verified_fact (or brief paraphrase); do not add outcomes."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(ugv_runner, session_id, message)
    tool_context.state["active_robot"] = "ugv"
    return {"success": True, "verified_fact": reply, "reply": reply, "target": "ugv"}


async def call_arm(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate to arm agent. Your reply MUST be only the returned verified_fact (or brief paraphrase); do not add outcomes."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(arm_runner, session_id, message)
    tool_context.state["active_robot"] = "arm"
    return {"success": True, "verified_fact": reply, "reply": reply, "target": "arm"}


def run_warehouse_command(
    tool_context: ToolContext,
    robot: str,
    action: str = "move",
    direction: Optional[str] = None,
    item_id: Optional[str] = None,
    stack_id: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute a single warehouse command, then verify state actually changed. Returns success, verified_fact, warehouse_state (verified snapshot), or error. Respond only with verified_fact or the error."""
    robot_key = (robot or "").strip().lower()
    action_key = (action or "move").strip().lower() or "move"
    direction_key = (direction and direction.strip().lower()) or None
    item_id_clean = (item_id and item_id.strip()) or None
    stack_id_clean = (stack_id and stack_id.strip()) or None
    state_before = get_state()
    try:
        out = execute_warehouse_command(
            robot=robot_key,
            action=action_key,
            direction=direction_key,
            item_id=item_id_clean,
            stack_id=stack_id_clean,
            x=x,
            y=y,
            z=z,
        )
    except ValueError as e:
        err = str(e)
        return {
            "success": False,
            "error": err,
            "verified_fact": f"Command failed: {err}",
        }
    # Verify state actually reflects the command
    state_after = get_state()
    ok, reason = verify_warehouse_state_after_command(
        robot_key,
        action_key,
        state_after,
        prev_state=state_before,
        direction=direction_key,
        item_id=item_id_clean,
        stack_id=stack_id_clean,
        x=x,
        y=y,
        z=z,
    )
    if not ok:
        err = f"State verification failed: {reason}. Do not claim the command succeeded."
        return {
            "success": False,
            "error": err,
            "verified_fact": err,
        }
    reply = out.get("reply", "")
    return {
        "success": True,
        "verified_fact": reply,
        "reply": reply,
        "robots": state_after.get("robots", []),
        "items": state_after.get("items", []),
        "warehouse_state": {
            "warehouse": state_after.get("warehouse", {}),
            "robots": state_after.get("robots", []),
            "items": state_after.get("items", []),
        },
    }


def get_robots_state(tool_context: ToolContext) -> Dict[str, Any]:
    """Return a snapshot of all robots with their positions, status, and current tasks. You may only report what is in the returned data; do not add or invent any robot or position."""
    state = get_state()
    robots: List[Dict[str, Any]] = state.get("robots", [])
    summary = [
        {
            "id": r.get("id"),
            "type": r.get("type"),
            "status": r.get("status"),
            "current_task": r.get("current_task"),
            "position": r.get("position"),
        }
        for r in robots
    ]
    return {
        "success": True,
        "verified_fact": "Report only the robot ids, positions, status, and current_task from the robots list below. Do not invent or add any robot or position.",
        "robots": summary,
        "warehouse": state.get("warehouse", {}),
    }


def get_warehouse_state(tool_context: ToolContext) -> Dict[str, Any]:
    """Return full warehouse state: robots, items, and bounds. You may only report what is in the returned data; do not add or invent any item or position."""
    state = get_state()
    return {
        "success": True,
        "verified_fact": "Report only the robots and items from the data below (ids, positions, stack_id). Do not invent or add any item or position.",
        "robots": state.get("robots", []),
        "items": state.get("items", []),
        "warehouse": state.get("warehouse", {}),
    }


WAREHOUSE_ORCHESTRATOR_INSTRUCTION = """
You are a warehouse robotics orchestrator. You manage three specialist robots: UAV (mapping), UGV (ground pick/drop/move), Arm (stacks).

ALWAYS use run_warehouse_command for these — the 3D view updates only when you use this tool (never use call_uav/call_ugv/call_arm for them):
- Any "move <robot> <direction>" or "<robot> move <direction>": e.g. "move ugv north", "move uav south", "ugv move east", "uav south", "move arm west" → run_warehouse_command(robot=ugv or uav or arm, action="move", direction=north or south or east or west). Extract robot and direction from the user message.
- "ugv pick item-1", "pick item-2" (UGV) → run_warehouse_command(robot="ugv", action="pick", item_id="item-1")
- "ugv drop item-1 at 10 5" → run_warehouse_command(robot="ugv", action="drop", item_id="item-1", x=10, z=5)
- "arm pick from stack stack-1" → run_warehouse_command(robot="arm", action="pick_from_stack", stack_id="stack-1")
- "arm place item-1 on stack stack-1" → run_warehouse_command(robot="arm", action="place_on_stack", stack_id="stack-1", item_id="item-1")

Use call_ugv / call_uav / call_arm ONLY for:
- "move ugv towards arm", "move towards arm" (not a cardinal direction) → call_ugv
- "scan the area", "find items", "map the warehouse" → call_uav
- Vague or multi-step requests → call the appropriate sub-agent

State and queries:
- get_robots_state: "what are robots doing?", "robot status", "where are the robots?"
- get_warehouse_state: "where are the items?", "inventory", "what items exist?"

You MUST call exactly one tool per user request; never answer from memory.

VALIDATION — no hallucination: Your reply MUST be based ONLY on the tool output.
- If the tool returned success=True and verified_fact: your reply MUST be that verified_fact (or a brief paraphrase in the user's language). Do not add positions, outcomes, or any fact not in verified_fact.
- If the tool returned success=False or an error: your reply MUST state that the command failed and include the error message. Do not claim success or invent an outcome.
- For get_robots_state / get_warehouse_state: report only what is in the returned data; do not invent any robot, item, or position.
Detect the user's language and respond in the SAME language. Keep replies concise and TTS-friendly.
"""


root_warehouse_orchestrator_agent = Agent(
    name="warehouse_orchestrator",
    model=MODEL,
    description="Routes warehouse tasks to UAV, UGV, or arm robot agents and can report robot/item state.",
    instruction=WAREHOUSE_ORCHESTRATOR_INSTRUCTION,
    tools=[run_warehouse_command, call_uav, call_ugv, call_arm, get_robots_state, get_warehouse_state],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.25,
    ),
)

