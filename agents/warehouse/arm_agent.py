import logging
import os
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext
from google.genai import types

_WAREHOUSE_DIR = os.path.dirname(os.path.abspath(__file__))
if _WAREHOUSE_DIR not in sys.path:
    sys.path.insert(0, _WAREHOUSE_DIR)

from state_store import get_state  # type: ignore[import-not-found]
from commands import execute_warehouse_command  # type: ignore[import-not-found]


load_dotenv()


logger = logging.getLogger("warehouse_arm_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


ARM_INSTRUCTION = """
You control a stationary manipulator arm that stacks and places items.

Response rule — no hallucination: You MUST respond ONLY from the last tool result.
- If the tool returned success=True and verified_fact: output exactly that verified_fact (or one short paraphrase in the user's language). Do not add positions or outcomes not in the tool output.
- If the tool returned success=False or an error: output only that the action failed and the error message. Do not claim success.
Never claim that an item was picked or placed unless you have just called the tool and are using only its verified_fact or error.

Tools:
- get_robots_positions(): positions of all robots (for planning).
- move_towards_robot(robot_id): one step toward ugv-1 or uav-1, stopping short.
- move_direction(direction): move 5 units north/south/east/west.
- move_arm(x, y, z): move end-effector to (x,y,z). Held item moves with arm.
- pick_from_stack(stack_id): pick top-most item from stack.
- place_on_stack(stack_id, item_id): place held item onto stack.
- get_stacks(): list stacks and items. Report only what is in the returned data.

Always match the user's language. Keep replies short and TTS-friendly.
"""


STEP = 5.0
MIN_DISTANCE_FROM_TARGET = 2.5


def move_towards_robot(tool_context: ToolContext, robot_id: str) -> Dict[str, Any]:
    """Move the arm one step (5 units) toward the given robot (ugv-1, uav-1), stopping short to avoid collision."""
    robot_id = (robot_id or "").strip().lower()
    if robot_id in ("arm", "arm-1"):
        return {"success": False, "error": "Cannot move towards self. Specify ugv-1 or uav-1.", "verified_fact": "Cannot move towards self. Specify ugv-1 or uav-1."}
    if robot_id in ("ugv", "ugv-1"):
        robot_id = "ugv-1"
    elif robot_id in ("uav", "uav-1"):
        robot_id = "uav-1"
    state = get_state()
    target_r = next((r for r in state.get("robots", []) if r.get("id") == robot_id), None)
    if not target_r:
        return {"success": False, "error": f"Robot '{robot_id}' not found.", "verified_fact": f"Robot '{robot_id}' not found. Use ugv-1 or uav-1."}
    tx, ty, tz = target_r.get("position") or [0.0, 0.0, 0.0]
    tx, ty, tz = float(tx), float(ty), float(tz)
    robots = state.get("robots", [])
    arm = next((r for r in robots if r.get("id") == "arm-1"), None)
    cx, cy, cz = (arm or {}).get("position", [25.0, 0.0, 10.0])
    dx, dy, dz = tx - cx, ty - cy, tz - cz
    dist = (dx * dx + dy * dy + dz * dz) ** 0.5
    if dist < 1e-6:
        return {"success": True, "verified_fact": "Already at target position.", "arm": arm}
    if dist <= MIN_DISTANCE_FROM_TARGET:
        return {"success": True, "verified_fact": f"Already within {MIN_DISTANCE_FROM_TARGET} units of {robot_id}.", "arm": arm}
    ux, uy, uz = dx / dist, dy / dist, dz / dist
    step = min(STEP, dist - MIN_DISTANCE_FROM_TARGET)
    if step < 0.5:
        return {"success": True, "verified_fact": f"Already near {robot_id}.", "arm": arm}
    new_x, new_y, new_z = cx + ux * step, cy + uy * step, cz + uz * step
    try:
        out = execute_warehouse_command("arm", "move", x=new_x, y=new_y, z=new_z)
        arm = next((r for r in out["robots"] if r.get("id") == "arm-1"), None)
        return {"success": True, "verified_fact": out["reply"], "arm": arm, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def move_direction(tool_context: ToolContext, direction: str) -> Dict[str, Any]:
    """Move the arm 5 units in a direction at current height: north (z-5), south (z+5), east (x+5), west (x-5)."""
    direction = (direction or "").strip().lower()
    if direction not in ("north", "south", "east", "west"):
        return {"success": False, "error": f"Direction must be north, south, east, or west. Got: {direction}", "verified_fact": f"Direction must be north, south, east, or west. Got: {direction}"}
    try:
        out = execute_warehouse_command("arm", "move", direction=direction)
        arm = next((r for r in out["robots"] if r.get("id") == "arm-1"), None)
        return {"success": True, "verified_fact": out["reply"], "arm": arm, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def get_robots_positions(tool_context: ToolContext) -> Dict[str, Any]:
    """Return positions of all robots. Use for planning; after calling move/pick/place, report only that tool's result."""
    state = get_state()
    robots = state.get("robots", [])
    positions = [{"id": r.get("id"), "type": r.get("type"), "position": list(r.get("position") or [0, 0, 0])} for r in robots]
    arm = next((r for r in robots if r.get("id") == "arm-1"), None)
    return {"success": True, "verified_fact": "Use all_robots for planning. After calling move/pick/place, report only that tool's verified_fact or error.", "arm_position": list((arm or {}).get("position", [25, 0, 10])), "all_robots": positions}


def move_arm(tool_context: ToolContext, x: float, y: float, z: float) -> Dict[str, Any]:
    """Move the arm end-effector to (x,y,z). Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("arm", "move", x=x, y=y, z=z)
        arm = next((r for r in out["robots"] if r.get("id") == "arm-1"), None)
        return {"success": True, "verified_fact": out["reply"], "arm": arm, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def pick_from_stack(tool_context: ToolContext, stack_id: str) -> Dict[str, Any]:
    """Pick the top-most item from the given stack. Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("arm", "pick_from_stack", stack_id=stack_id)
        return {"success": True, "verified_fact": out["reply"], "picked_item": out.get("items"), "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def place_on_stack(tool_context: ToolContext, stack_id: str, item_id: str) -> Dict[str, Any]:
    """Place an item onto the named stack. Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("arm", "place_on_stack", stack_id=stack_id, item_id=item_id)
        return {"success": True, "verified_fact": out["reply"], "stack_id": stack_id, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def get_stacks(tool_context: ToolContext) -> Dict[str, Any]:
    """Summarize stacks and their items. Report only what is in the returned data."""
    state = get_state()
    stacks: Dict[str, Dict[str, Any]] = {}
    for it in state.get("items", []):
        sid = it.get("stack_id")
        if not sid:
            continue
        s = stacks.setdefault(
            sid,
            {"stack_id": sid, "items": [], "count": 0},
        )
        s["items"].append(it)
        s["count"] += 1
    return {"success": True, "verified_fact": "Report only the stacks and items from the data below. Do not invent or add any stack or item.", "stacks": list(stacks.values())}


root_arm_agent = Agent(
    name="warehouse_arm",
    model=MODEL,
    description="Arm that stacks and places items on shelves.",
    instruction=ARM_INSTRUCTION,
    tools=[get_robots_positions, move_towards_robot, move_direction, move_arm, pick_from_stack, place_on_stack, get_stacks],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.25,
    ),
)

