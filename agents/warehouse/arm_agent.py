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

from state_store import (  # type: ignore[import-not-found]
    get_state,
    get_warehouse_bounds,
    is_within_bounds,
    update_robot_position,
    update_robot_status,
    upsert_item,
)


load_dotenv()


logger = logging.getLogger("warehouse_arm_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


ARM_INSTRUCTION = """
You control a stationary manipulator arm that stacks and places items.

- Always match the user's language.
- Keep replies short and suitable for TTS.

Tools:
- move_arm(x, y, z): move the arm's end-effector in 3D space.
- pick_from_stack(stack_id): pick the top-most item from a stack.
- place_on_stack(stack_id, item_id): place an item onto a stack, increasing its height.
- get_stacks(): list stacks and their items.

Stacks are represented by items that share the same stack_id. The item height is based on how many items are already in that stack.
You MUST call these tools to move the arm or modify stacks; never claim that an item was picked or placed
unless you have just used the appropriate tool and you are describing its result.
"""


def _stack_height(stack_id: str) -> int:
    state = get_state()
    items: List[Dict[str, Any]] = state.get("items", [])
    return sum(1 for it in items if it.get("stack_id") == stack_id)


def _get_holding_item() -> str | None:
    """Return item_id if arm is holding an item, else None."""
    state = get_state()
    for r in state.get("robots", []):
        if r.get("id") == "arm-1":
            task = r.get("current_task") or ""
            if task.startswith("holding_"):
                return task.replace("holding_", "").strip()
    return None


def _get_stack_base(stack_id: str) -> Tuple[float, float]:
    """Return (x, z) base position for a stack."""
    state = get_state()
    items: List[Dict[str, Any]] = state.get("items", [])
    stack_items = [it for it in items if it.get("stack_id") == stack_id]
    if stack_items:
        pos = stack_items[0].get("position") or [25.0, 0.0, 10.0]
        return float(pos[0]), float(pos[2])
    return 25.0, 10.0


def move_arm(tool_context: ToolContext, x: float, y: float, z: float) -> Dict[str, Any]:
    """Move the arm end-effector to a new 3D position. Held item moves with it."""
    if not is_within_bounds(x, y, z):
        w, d, h = get_warehouse_bounds()
        return {"error": f"Position ({x}, {y}, {z}) is outside warehouse bounds (0–{w} x 0–{d} x 0–{h})."}
    arm = update_robot_position("arm-1", x, y, z)
    holding = _get_holding_item()
    if holding:
        upsert_item(holding, (x, y, z), stack_id=None)
        update_robot_status("arm-1", "working", current_task=f"holding_{holding}")
    else:
        update_robot_status("arm-1", "moving", current_task=f"moving_to_{x:.1f}_{y:.1f}_{z:.1f}")
    return {"arm": arm}


def pick_from_stack(tool_context: ToolContext, stack_id: str) -> Dict[str, Any]:
    """Pick the top-most item from the given stack (if any)."""
    holding = _get_holding_item()
    if holding:
        return {"error": f"Arm is already holding '{holding}'. Place it on a stack first before picking another."}
    state = get_state()
    items: List[Dict[str, Any]] = state.get("items", [])
    stack_items = [it for it in items if it.get("stack_id") == stack_id]
    if not stack_items:
        return {"error": f"No items found in stack '{stack_id}'."}

    # Use the last item in the stack as the top for this simple demo.
    item = stack_items[-1]
    item_id = str(item.get("id"))
    # Move item to arm position and clear stack_id.
    for r in state.get("robots", []):
        if r.get("id") == "arm-1":
            ax, ay, az = r.get("position", [25.0, 0.0, 10.0])
            updated_item = upsert_item(item_id, (ax, ay, az), stack_id=None)
            update_robot_status("arm-1", "working", current_task=f"holding_{item_id}")
            return {"picked_item": updated_item}

    # Fallback if arm not found.
    updated_item = upsert_item(item_id, (25.0, 0.0, 10.0), stack_id=None)
    update_robot_status("arm-1", "working", current_task=f"holding_{item_id}")
    return {"picked_item": updated_item}


def place_on_stack(tool_context: ToolContext, stack_id: str, item_id: str) -> Dict[str, Any]:
    """Place an item onto the named stack, updating its vertical position."""
    holding = _get_holding_item()
    if holding != item_id:
        return {
            "error": f"Arm is not holding '{item_id}'." + (f" (Currently holding '{holding}')" if holding else ""),
        }
    level = _stack_height(stack_id)
    base_x, base_z = _get_stack_base(stack_id)
    y = 0.5 * (level + 1)
    if not is_within_bounds(base_x, y, base_z):
        w, d, h = get_warehouse_bounds()
        return {"error": f"Stack position would be outside warehouse bounds (0–{w} x 0–{d} x 0–{h})."}
    updated_item = upsert_item(item_id, (base_x, y, base_z), stack_id=stack_id)
    update_robot_status("arm-1", "idle", current_task=None)
    return {"stack_id": stack_id, "item": updated_item, "stack_level": level + 1}


def get_stacks(tool_context: ToolContext) -> Dict[str, Any]:
    """Summarize stacks and their items."""
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
    return {"stacks": list(stacks.values())}


root_arm_agent = Agent(
    name="warehouse_arm",
    model=MODEL,
    description="Arm that stacks and places items on shelves.",
    instruction=ARM_INSTRUCTION,
    tools=[move_arm, pick_from_stack, place_on_stack, get_stacks],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.25,
    ),
)

