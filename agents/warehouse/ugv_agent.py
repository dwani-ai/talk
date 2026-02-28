import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

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
    get_warehouse_bounds,
    is_within_bounds,
    update_robot_position,
    update_robot_status,
    upsert_item,
)


load_dotenv()


logger = logging.getLogger("warehouse_ugv_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


UGV_INSTRUCTION = """
You control a UGV (ground robot) that moves items around the warehouse floor.

- Always answer in the same language as the user.
- Keep replies short and easy for TTS.

Capabilities via tools:
- move_to(x, z): drive the UGV on the ground plane (y is always 0).
- pick_item(item_id): pick up an item so that it moves with the robot.
- drop_item(item_id, x, z): place the carried item at a ground position.
- get_nearby_items(radius): list items within a radius of the robot.

You MUST use these tools to change positions or move items; do not pretend you moved without calling a tool.
Never say the UGV moved, picked, or dropped anything unless you have just called the corresponding tool
and you base your answer on its returned position or item data.
"""


def _get_ugv_pose() -> Tuple[float, float, float]:
    state = get_state()
    for r in state.get("robots", []):
        if r.get("id") == "ugv-1":
            x, y, z = r.get("position", [0.0, 0.0, 0.0])
            return float(x), float(y), float(z)
    return 5.0, 0.0, 5.0


def _get_item_held_by(item_id: str) -> Optional[str]:
    """Return robot_id if any robot is carrying/holding this item, else None."""
    state = get_state()
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


def _get_carried_item() -> Optional[str]:
    """Return item_id if UGV is carrying an item, else None."""
    state = get_state()
    for r in state.get("robots", []):
        if r.get("id") == "ugv-1":
            task = r.get("current_task") or ""
            if task.startswith("carrying_"):
                return task.replace("carrying_", "").strip()
    return None


def move_to(tool_context: ToolContext, x: float, z: float) -> Dict[str, Any]:
    """Move the UGV on the ground plane to (x, 0, z). Carried item moves with it."""
    if not is_within_bounds(x, 0.0, z):
        w, d, _ = get_warehouse_bounds()
        return {"error": f"Position ({x}, {z}) is outside warehouse bounds (0–{w} x 0–{d})."}
    robot = update_robot_position("ugv-1", x, 0.0, z)
    carried = _get_carried_item()
    if carried:
        upsert_item(carried, (x, 0.0, z), stack_id=None)
        update_robot_status("ugv-1", "working", current_task=f"carrying_{carried}")
    else:
        update_robot_status("ugv-1", "moving", current_task=f"driving_to_{x:.1f}_{z:.1f}")
    return {"ugv": robot}


def pick_item(tool_context: ToolContext, item_id: str) -> Dict[str, Any]:
    """Pick an item so that it moves with the UGV."""
    carried = _get_carried_item()
    if carried:
        return {"error": f"UGV is already carrying '{carried}'. Drop it first before picking another."}
    state = get_state()
    items: List[Dict[str, Any]] = state.get("items", [])
    item = next((it for it in items if it.get("id") == item_id), None)
    if item is None:
        return {"error": f"Item '{item_id}' not found."}
    if item.get("stack_id"):
        return {"error": f"Item '{item_id}' is on a stack. Use arm to pick from stack."}
    held_by = _get_item_held_by(item_id)
    if held_by:
        return {"error": f"Item '{item_id}' is already held by {held_by}. It must be released first."}

    x, _, z = _get_ugv_pose()
    updated_item = upsert_item(item_id, (x, 0.0, z), stack_id=None)
    update_robot_status("ugv-1", "working", current_task=f"carrying_{item_id}")
    return {"carried_item": updated_item}


def drop_item(tool_context: ToolContext, item_id: str, x: float, z: float) -> Dict[str, Any]:
    """Drop the carried item at a new ground position."""
    carried = _get_carried_item()
    if carried != item_id:
        return {
            "error": f"UGV is not carrying '{item_id}'." + (f" (Currently carrying '{carried}')" if carried else ""),
        }
    if not is_within_bounds(x, 0.0, z):
        w, d, _ = get_warehouse_bounds()
        return {"error": f"Drop position ({x}, {z}) is outside warehouse bounds (0–{w} x 0–{d})."}
    updated_item = upsert_item(item_id, (x, 0.0, z), stack_id=None)
    update_robot_status("ugv-1", "idle", current_task=None)
    return {"dropped_item": updated_item}


def get_nearby_items(tool_context: ToolContext, radius: float = 3.0) -> Dict[str, Any]:
    """Return items within a given radius of the UGV."""
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
    return {"ugv_position": [sx, 0.0, sz], "nearby_items": nearby}


root_ugv_agent = Agent(
    name="warehouse_ugv",
    model=MODEL,
    description="UGV that moves items on the warehouse floor.",
    instruction=UGV_INSTRUCTION,
    tools=[move_to, pick_item, drop_item, get_nearby_items],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.25,
    ),
)

