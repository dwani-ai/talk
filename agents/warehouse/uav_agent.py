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
    update_robot_position,
    update_robot_status,
    upsert_item,
)


load_dotenv()


logger = logging.getLogger("warehouse_uav_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


UAV_INSTRUCTION = """
You control a UAV (drone) that maps items inside a warehouse.

- Users may speak or type in many languages; always answer in the SAME language as the user.
- Keep responses short and TTS-friendly (one or two short sentences).
- You must use tools to move or scan; do not invent state changes.

Tools:
- move_to(x, y, z): fly the UAV to a 3D position inside the warehouse.
- scan_area(x_min, y_min, x_max, y_max): scan a rectangular ground area and update the item map.
- get_map(): return the current known items and UAV pose.

Typical flow:
1) Move close to the requested region with move_to.
2) Scan the region with scan_area.
3) Summarize what you found using get_map.
"""


def move_to(tool_context: ToolContext, x: float, y: float, z: float) -> Dict[str, Any]:
    """Move the UAV to a new 3D position."""
    robot = update_robot_position("uav-1", x, y, z)
    update_robot_status("uav-1", "moving", current_task=f"flying_to_{x:.1f}_{y:.1f}_{z:.1f}")
    return {"uav": robot}


def scan_area(
    tool_context: ToolContext,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> Dict[str, Any]:
    """Scan a ground rectangle and synthesize a few demo items inside it."""
    # Mark UAV as working over the center of the area.
    cx = (x_min + x_max) / 2.0
    cy = (y_min + y_max) / 2.0
    update_robot_position("uav-1", cx, 5.0, cy)
    update_robot_status("uav-1", "working", current_task="scanning_area")

    # Create a couple of synthetic items in the scanned region for visualization.
    created_items: List[Dict[str, Any]] = []
    created_items.append(upsert_item(f"scan-item-{int(cx)}-{int(cy)}", (cx, 0.0, cy), None))
    created_items.append(
        upsert_item(f"scan-item-{int(x_min)}-{int(y_min)}", (x_min, 0.0, y_min), None)
    )
    state_after = get_state()
    return {
        "uav": next(r for r in state_after["robots"] if r.get("id") == "uav-1"),
        "created_items": created_items,
        "items_total": len(state_after.get("items", [])),
    }


def get_map(tool_context: ToolContext) -> Dict[str, Any]:
    """Return a snapshot of the current warehouse items and UAV pose."""
    state = get_state()
    robots = state.get("robots", [])
    uav = next((r for r in robots if r.get("id") == "uav-1"), None)
    return {
        "uav": uav,
        "items": state.get("items", []),
        "warehouse": state.get("warehouse", {}),
    }


root_uav_agent = Agent(
    name="warehouse_uav",
    model=MODEL,
    description="UAV drone that maps items inside the warehouse.",
    instruction=UAV_INSTRUCTION,
    tools=[move_to, scan_area, get_map],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
    ),
)

