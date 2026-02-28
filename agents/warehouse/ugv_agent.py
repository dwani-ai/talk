import logging
import os
import sys
from typing import Any, Dict, List, Tuple

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


logger = logging.getLogger("warehouse_ugv_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


UGV_INSTRUCTION = """
You control a UGV (ground robot) that moves items around the warehouse floor.

Response rule — no hallucination: You MUST respond ONLY from the last tool result.
- If the tool returned success=True and verified_fact: output exactly that verified_fact (or one short sentence paraphrase in the user's language). Do not add positions or outcomes not in the tool output.
- If the tool returned success=False or an error: output only that the action failed and the error message. Do not claim success.
You MUST call a tool before any claim about movement, pick, or drop. Never say the UGV moved, picked, or dropped without having just called the corresponding tool and using only its verified_fact or error.

Tools:
- get_robots_positions(): positions of all robots (for planning).
- move_towards_robot(robot_id): one step toward arm-1 or uav-1, stopping short. Use for "move towards arm". Call repeatedly to get closer.
- move_direction(direction): move 5 units north/south/east/west.
- move_to(x, z): drive to (x, z) on the ground. Carried item moves with UGV.
- pick_item(item_id): pick up item. Uses deterministic API.
- drop_item(item_id, x, z): drop carried item at (x, z).
- get_nearby_items(radius): items within radius of UGV.

Always answer in the same language as the user. Keep replies short and TTS-friendly.
"""


def _get_ugv_pose() -> Tuple[float, float, float]:
    state = get_state()
    for r in state.get("robots", []):
        if r.get("id") == "ugv-1":
            x, y, z = r.get("position", [0.0, 0.0, 0.0])
            return float(x), float(y), float(z)
    return 5.0, 0.0, 5.0


STEP = 5.0
MIN_DISTANCE_FROM_TARGET = 2.5  # stay at least this far from another robot when moving "towards" it


def move_towards_robot(tool_context: ToolContext, robot_id: str) -> Dict[str, Any]:
    """Move the UGV one step (5 units) toward the given robot (arm-1, uav-1, etc.), stopping short to avoid collision. Call repeatedly to get closer. Returns success, verified_fact (only sentence you may say), or error."""
    robot_id = (robot_id or "").strip().lower()
    if robot_id == "ugv-1" or robot_id == "ugv":
        return {"success": False, "error": "Cannot move towards self. Specify arm-1 or uav-1.", "verified_fact": "Cannot move towards self. Specify arm-1 or uav-1."}
    if robot_id in ("arm", "arm-1"):
        robot_id = "arm-1"
    elif robot_id in ("uav", "uav-1"):
        robot_id = "uav-1"
    state = get_state()
    target_r = next((r for r in state.get("robots", []) if r.get("id") == robot_id), None)
    if not target_r:
        return {"success": False, "error": f"Robot '{robot_id}' not found.", "verified_fact": f"Robot '{robot_id}' not found. Use arm-1 or uav-1."}
    tx, ty, tz = target_r.get("position") or [0.0, 0.0, 0.0]
    tx, tz = float(tx), float(tz)
    cx, _, cz = _get_ugv_pose()
    dx, dz = tx - cx, tz - cz
    dist = (dx * dx + dz * dz) ** 0.5
    robots = state.get("robots", [])
    ugv_now = next((r for r in robots if r.get("id") == "ugv-1"), None)
    if dist < 1e-6:
        return {"success": True, "verified_fact": "Already at target position.", "ugv": ugv_now}
    if dist <= MIN_DISTANCE_FROM_TARGET:
        msg = f"Already within {MIN_DISTANCE_FROM_TARGET} units of {robot_id}. Safe distance maintained."
        return {"success": True, "verified_fact": msg, "ugv": ugv_now}
    ux, uz = dx / dist, dz / dist
    step = min(STEP, dist - MIN_DISTANCE_FROM_TARGET)
    if step < 0.5:
        return {"success": True, "verified_fact": f"Already near {robot_id}. Safe distance maintained.", "ugv": ugv_now}
    new_x, new_z = cx + ux * step, cz + uz * step
    try:
        out = execute_warehouse_command("ugv", "move", x=new_x, y=0.0, z=new_z)
        ugv = next((r for r in out["robots"] if r.get("id") == "ugv-1"), None)
        return {"success": True, "verified_fact": out["reply"], "ugv": ugv, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def move_direction(tool_context: ToolContext, direction: str) -> Dict[str, Any]:
    """Move the UGV 5 units in a direction: north (z-5), south (z+5), east (x+5), west (x-5). Returns success and verified_fact or error."""
    direction = (direction or "").strip().lower()
    if direction not in ("north", "south", "east", "west"):
        return {"success": False, "error": f"Direction must be north, south, east, or west. Got: {direction}", "verified_fact": f"Direction must be north, south, east, or west. Got: {direction}"}
    try:
        out = execute_warehouse_command("ugv", "move", direction=direction)
        ugv = next((r for r in out["robots"] if r.get("id") == "ugv-1"), None)
        return {"success": True, "verified_fact": out["reply"], "ugv": ugv, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def move_to(tool_context: ToolContext, x: float, z: float) -> Dict[str, Any]:
    """Move the UGV on the ground plane to (x, 0, z). Carried item moves with it. Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("ugv", "move", x=x, y=0.0, z=z)
        ugv = next((r for r in out["robots"] if r.get("id") == "ugv-1"), None)
        return {"success": True, "verified_fact": out["reply"], "ugv": ugv, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def pick_item(tool_context: ToolContext, item_id: str) -> Dict[str, Any]:
    """Pick an item (UGV moves to it first, then picks). Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("ugv", "pick", item_id=item_id)
        ugv = next((r for r in out["robots"] if r.get("id") == "ugv-1"), None)
        return {"success": True, "verified_fact": out["reply"], "ugv": ugv, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def drop_item(tool_context: ToolContext, item_id: str, x: float, z: float) -> Dict[str, Any]:
    """Drop the carried item at (x, z). Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("ugv", "drop", item_id=item_id, x=x, z=z)
        ugv = next((r for r in out["robots"] if r.get("id") == "ugv-1"), None)
        return {"success": True, "verified_fact": out["reply"], "ugv": ugv, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def get_nearby_items(tool_context: ToolContext, radius: float = 3.0) -> Dict[str, Any]:
    """Return items within a given radius of the UGV. Use for planning; then call pick_item or move. Report only the result of the action tool."""
    sx, _, sz = _get_ugv_pose()
    state = get_state()
    items: List[Dict[str, Any]] = state.get("items", [])
    nearby: List[Dict[str, Any]] = []
    r2 = float(radius) * float(radius)
    for it in items:
        ix, iy, iz = it.get("position", [0.0, 0.0, 0.0])
        dx = float(ix) - sx
        dz = float(iz) - sz
        if dx * dx + dz * dz <= r2:
            nearby.append(it)
    return {"success": True, "verified_fact": "Use nearby_items for planning. After calling pick_item or move, report only that tool's verified_fact or error.", "ugv_position": [sx, 0.0, sz], "nearby_items": nearby}


def get_robots_positions(tool_context: ToolContext) -> Dict[str, Any]:
    """Return positions of all robots. Use for planning; after calling move/pick/drop, report only that tool's result."""
    state = get_state()
    robots: List[Dict[str, Any]] = state.get("robots", [])
    positions = []
    for r in robots:
        rid = r.get("id")
        pos = r.get("position") or [0.0, 0.0, 0.0]
        positions.append({"id": rid, "type": r.get("type"), "position": list(pos)})
    ugv_pos = _get_ugv_pose()
    return {"success": True, "verified_fact": "Use all_robots for planning. After calling a move/pick/drop tool, report only that tool's verified_fact or error.", "ugv_position": list(ugv_pos), "all_robots": positions}


root_ugv_agent = Agent(
    name="warehouse_ugv",
    model=MODEL,
    description="UGV that moves items on the warehouse floor.",
    instruction=UGV_INSTRUCTION,
    tools=[get_robots_positions, move_towards_robot, move_direction, move_to, pick_item, drop_item, get_nearby_items],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.25,
    ),
)

