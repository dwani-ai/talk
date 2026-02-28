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
"""


def _stack_height(stack_id: str) -> int:
    state = get_state()
    items: List[Dict[str, Any]] = state.get("items", [])
    return sum(1 for it in items if it.get("stack_id") == stack_id)


def move_arm(tool_context: ToolContext, x: float, y: float, z: float) -> Dict[str, Any]:
    """Move the arm end-effector to a new 3D position."""
    arm = update_robot_position("arm-1", x, y, z)
    update_robot_status("arm-1", "moving", current_task=f"moving_to_{x:.1f}_{y:.1f}_{z:.1f}")
    return {"arm": arm}


def pick_from_stack(tool_context: ToolContext, stack_id: str) -> Dict[str, Any]:
    """Pick the top-most item from the given stack (if any)."""
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
    level = _stack_height(stack_id)
    base_x, base_z = 25.0, 10.0
    y = 0.5 * (level + 1)
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

