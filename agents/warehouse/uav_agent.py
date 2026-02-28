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

from state_store import (  # type: ignore[import-not-found]
    get_state,
    position_occupied_by_other,
    update_robot_position,
    update_robot_status,
    upsert_item,
)
from commands import execute_warehouse_command  # type: ignore[import-not-found]


load_dotenv()


logger = logging.getLogger("warehouse_uav_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


UAV_INSTRUCTION = """
You control a UAV (drone) that maps items inside a warehouse.

Response rule — no hallucination: You MUST respond ONLY from the last tool result.
- If the tool returned success=True and verified_fact: output exactly that verified_fact (or one short paraphrase in the user's language). Do not add positions or outcomes not in the tool output.
- If the tool returned success=False or an error: output only that the action failed and the error message. Do not claim success.
Never say the UAV moved, scanned, or found items unless you have just called the tool and are using only its verified_fact or error.

Tools:
- get_robots_positions(): positions of all robots (for planning).
- move_towards_robot(robot_id): fly one step toward arm-1 or ugv-1, stopping short.
- move_direction(direction): fly 5 units north/south/east/west at height 5.
- move_to(x, y, z): fly to 3D position. Collision check enforced.
- scan_area(x_min, y_min, x_max, y_max): scan a ground rectangle and update the item map.
- get_map(): current items and UAV pose. Report only what is in the returned data.

Always answer in the same language as the user. Keep replies short and TTS-friendly.
"""


STEP = 5.0
UAV_HEIGHT = 5.0
MIN_DISTANCE_FROM_TARGET = 2.5


def move_towards_robot(tool_context: ToolContext, robot_id: str) -> Dict[str, Any]:
    """Fly one step (5 units) toward the given robot (arm-1, ugv-1), at UAV height. Stops short to avoid collision."""
    robot_id = (robot_id or "").strip().lower()
    if robot_id in ("uav", "uav-1"):
        return {"success": False, "error": "Cannot move towards self. Specify arm-1 or ugv-1.", "verified_fact": "Cannot move towards self. Specify arm-1 or ugv-1."}
    if robot_id in ("arm", "arm-1"):
        robot_id = "arm-1"
    elif robot_id in ("ugv", "ugv-1"):
        robot_id = "ugv-1"
    state = get_state()
    target_r = next((r for r in state.get("robots", []) if r.get("id") == robot_id), None)
    if not target_r:
        return {"success": False, "error": f"Robot '{robot_id}' not found.", "verified_fact": f"Robot '{robot_id}' not found. Use arm-1 or ugv-1."}
    tx, ty, tz = target_r.get("position") or [0.0, 0.0, 0.0]
    tx, ty, tz = float(tx), float(ty), float(tz)
    # Move toward (tx, UAV_HEIGHT, tz) to stay at flight height
    robots = state.get("robots", [])
    uav = next((r for r in robots if r.get("id") == "uav-1"), None)
    cx, cy, cz = (uav or {}).get("position", [10.0, 5.0, 5.0])
    dx, dz = tx - cx, tz - cz
    dist_2d = (dx * dx + dz * dz) ** 0.5
    if dist_2d < 1e-6:
        return {"success": True, "verified_fact": "Already above target position.", "uav": uav}
    ux, uz = dx / dist_2d, dz / dist_2d
    step = min(STEP, max(0, dist_2d - MIN_DISTANCE_FROM_TARGET))
    if step < 0.5:
        return {"success": True, "verified_fact": f"Already within {MIN_DISTANCE_FROM_TARGET} units of {robot_id}.", "uav": uav}
    new_x = cx + ux * step
    new_z = cz + uz * step
    try:
        out = execute_warehouse_command("uav", "move", x=new_x, y=UAV_HEIGHT, z=new_z)
        uav = next((r for r in out["robots"] if r.get("id") == "uav-1"), None)
        return {"success": True, "verified_fact": out["reply"], "uav": uav, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def move_direction(tool_context: ToolContext, direction: str) -> Dict[str, Any]:
    """Move the UAV 5 units in a direction at height 5: north (z-5), south (z+5), east (x+5), west (x-5)."""
    direction = (direction or "").strip().lower()
    if direction not in ("north", "south", "east", "west"):
        return {"success": False, "error": f"Direction must be north, south, east, or west. Got: {direction}", "verified_fact": f"Direction must be north, south, east, or west. Got: {direction}"}
    try:
        out = execute_warehouse_command("uav", "move", direction=direction)
        uav = next((r for r in out["robots"] if r.get("id") == "uav-1"), None)
        return {"success": True, "verified_fact": out["reply"], "uav": uav, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def get_robots_positions(tool_context: ToolContext) -> Dict[str, Any]:
    """Return positions of all robots. Use for planning; after calling move/scan, report only that tool's result."""
    state = get_state()
    robots = state.get("robots", [])
    positions = [{"id": r.get("id"), "type": r.get("type"), "position": list(r.get("position") or [0, 0, 0])} for r in robots]
    uav = next((r for r in robots if r.get("id") == "uav-1"), None)
    return {"success": True, "verified_fact": "Use all_robots for planning. After calling move or scan, report only that tool's verified_fact or error.", "uav_position": list((uav or {}).get("position", [10, 5, 5])), "all_robots": positions}


def move_to(tool_context: ToolContext, x: float, y: float, z: float) -> Dict[str, Any]:
    """Move the UAV to a new 3D position. Returns success, verified_fact, or error."""
    try:
        out = execute_warehouse_command("uav", "move", x=x, y=y, z=z)
        uav = next((r for r in out["robots"] if r.get("id") == "uav-1"), None)
        return {"success": True, "verified_fact": out["reply"], "uav": uav, "reply": out["reply"]}
    except ValueError as e:
        err = str(e)
        return {"success": False, "error": err, "verified_fact": f"Failed: {err}"}


def scan_area(
    tool_context: ToolContext,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> Dict[str, Any]:
    """Scan a ground rectangle and synthesize a few demo items inside it."""
    cx = (x_min + x_max) / 2.0
    cy = (y_min + y_max) / 2.0
    occupant = position_occupied_by_other("uav-1", cx, 5.0, cy)
    if occupant:
        err = f"Scan area center ({cx}, 5, {cy}) occupied by {occupant['id']}. Choose another area."
        return {"success": False, "error": err, "verified_fact": err}
    update_robot_position("uav-1", cx, 5.0, cy)
    update_robot_status("uav-1", "working", current_task="scanning_area")

    # Create a couple of synthetic items in the scanned region for visualization.
    created_items: List[Dict[str, Any]] = []
    created_items.append(upsert_item(f"scan-item-{int(cx)}-{int(cy)}", (cx, 0.0, cy), None))
    created_items.append(
        upsert_item(f"scan-item-{int(x_min)}-{int(y_min)}", (x_min, 0.0, y_min), None)
    )
    state_after = get_state()
    uav_r = next(r for r in state_after["robots"] if r.get("id") == "uav-1")
    fact = f"Scanned area; UAV at [{uav_r['position'][0]}, {uav_r['position'][1]}, {uav_r['position'][2]}]. Created {len(created_items)} items; total items: {len(state_after.get('items', []))}."
    return {
        "success": True,
        "verified_fact": fact,
        "uav": uav_r,
        "created_items": created_items,
        "items_total": len(state_after.get("items", [])),
    }


def get_map(tool_context: ToolContext) -> Dict[str, Any]:
    """Return current items and UAV pose. Report only what is in the returned data; do not invent items or positions."""
    state = get_state()
    robots = state.get("robots", [])
    uav = next((r for r in robots if r.get("id") == "uav-1"), None)
    items = state.get("items", [])
    return {
        "success": True,
        "verified_fact": "Report only the UAV position and the items list below (id, position, stack_id). Do not invent or add any item or position.",
        "uav": uav,
        "items": items,
        "warehouse": state.get("warehouse", {}),
    }


root_uav_agent = Agent(
    name="warehouse_uav",
    model=MODEL,
    description="UAV drone that maps items inside the warehouse.",
    instruction=UAV_INSTRUCTION,
    tools=[get_robots_positions, move_towards_robot, move_direction, move_to, scan_area, get_map],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
    ),
)

