import threading
import sys
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

# Ensure a single shared module instance regardless of import style
# (state_store vs warehouse.state_store), otherwise robot state can split.
_this_module = sys.modules[__name__]
sys.modules.setdefault("state_store", _this_module)
sys.modules.setdefault("warehouse.state_store", _this_module)

# Sentinel: when passed to upsert_robot, means "do not change this field"
_UNSET = object()

_lock = threading.Lock()


_state: Dict[str, Any] = {
    "warehouse": {
        "width": 50.0,
        "depth": 30.0,
        "height": 10.0,
    },
    "robots": [],
    "items": [],
}


def _init_default_state() -> None:
    """Initialize a simple default warehouse with one robot of each type and a few items."""
    with _lock:
        _state["robots"] = [
            {
                "id": "uav-1",
                "type": "uav",
                "position": [10.0, 5.0, 5.0],
                "orientation": [0.0, 0.0, 0.0],
                "status": "idle",
                "current_task": None,
            },
            {
                "id": "ugv-1",
                "type": "ugv",
                "position": [5.0, 0.0, 5.0],
                "orientation": [0.0, 0.0, 0.0],
                "status": "idle",
                "current_task": None,
            },
            {
                "id": "arm-1",
                "type": "arm",
                "position": [25.0, 0.0, 10.0],
                "orientation": [0.0, 0.0, 0.0],
                "status": "idle",
                "current_task": None,
            },
        ]

        _state["items"] = [
            {
                "id": "item-1",
                "position": [8.0, 0.0, 6.0],
                "stack_id": None,
            },
            {
                "id": "item-2",
                "position": [12.0, 0.0, 12.0],
                "stack_id": None,
            },
            {
                "id": "item-3",
                "position": [25.0, 0.0, 10.0],
                "stack_id": "stack-1",
            },
        ]


_init_default_state()


def get_state() -> Dict[str, Any]:
    """Return a snapshot of the current warehouse state."""
    with _lock:
        return deepcopy(_state)


def _find_robot_index(robot_id: str) -> int:
    for idx, robot in enumerate(_state.get("robots", [])):
        if robot.get("id") == robot_id:
            return idx
    return -1


def upsert_robot(
    robot_id: str,
    robot_type: Optional[str] = None,
    position: Optional[Tuple[float, float, float]] = None,
    orientation: Optional[Tuple[float, float, float]] = None,
    status: Optional[str] = _UNSET,
    current_task: Optional[str] = _UNSET,
) -> Dict[str, Any]:
    """Create or update a robot entry in the state store. Use _UNSET for status/current_task to leave them unchanged."""
    with _lock:
        robots: List[Dict[str, Any]] = _state.setdefault("robots", [])
        idx = _find_robot_index(robot_id)
        if idx == -1:
            robot: Dict[str, Any] = {
                "id": robot_id,
                "type": robot_type or "unknown",
                "position": list(position) if position is not None else [0.0, 0.0, 0.0],
                "orientation": list(orientation) if orientation is not None else [0.0, 0.0, 0.0],
                "status": status if status is not _UNSET else "idle",
                "current_task": current_task if current_task is not _UNSET else None,
            }
            robots.append(robot)
        else:
            robot = robots[idx]
            if robot_type is not None:
                robot["type"] = robot_type
            if position is not None:
                robot["position"] = list(position)
            if orientation is not None:
                robot["orientation"] = list(orientation)
            if status is not _UNSET:
                robot["status"] = status
            if current_task is not _UNSET:
                robot["current_task"] = current_task

        return deepcopy(robot)


def update_robot_position(robot_id: str, x: float, y: float, z: float) -> Dict[str, Any]:
    return upsert_robot(robot_id, position=(x, y, z))


def update_robot_status(robot_id: str, status: str, current_task: Optional[str] = _UNSET) -> Dict[str, Any]:
    """Update robot status. Pass current_task=None to clear, or omit to leave unchanged."""
    return upsert_robot(robot_id, status=status, current_task=current_task)


def upsert_item(
    item_id: str,
    position: Tuple[float, float, float],
    stack_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update an item entry in the state store."""
    with _lock:
        items: List[Dict[str, Any]] = _state.setdefault("items", [])
        existing = next((it for it in items if it.get("id") == item_id), None)
        if existing is None:
            existing = {"id": item_id}
            items.append(existing)
        existing["position"] = list(position)
        existing["stack_id"] = stack_id
        return deepcopy(existing)


def remove_item(item_id: str) -> bool:
    """Remove an item by id. Returns True if it existed."""
    with _lock:
        items: List[Dict[str, Any]] = _state.setdefault("items", [])
        before = len(items)
        _state["items"] = [it for it in items if it.get("id") != item_id]
        return len(_state["items"]) < before


def reset_state() -> None:
    """Reset to the default demo state."""
    _init_default_state()


def get_warehouse_bounds() -> Tuple[float, float, float]:
    """Return (width, depth, height) of the warehouse."""
    wh = _state.get("warehouse", {})
    return (
        float(wh.get("width", 50.0)),
        float(wh.get("depth", 30.0)),
        float(wh.get("height", 10.0)),
    )


def is_within_bounds(x: float, y: float, z: float) -> bool:
    """Check if a point is within warehouse bounds."""
    w, d, h = get_warehouse_bounds()
    return 0 <= x <= w and 0 <= z <= d and 0 <= y <= h


def position_occupied_by_other(
    robot_id: str,
    x: float,
    y: float,
    z: float,
    tolerance: float = 2.0,
) -> Optional[Dict[str, Any]]:
    """Return the other robot that would be collided with at (x,y,z), or None. Uses 3D distance."""
    with _lock:
        robots = _state.get("robots", [])
        for r in robots:
            rid = r.get("id")
            if rid == robot_id:
                continue
            pos = r.get("position") or [0.0, 0.0, 0.0]
            rx, ry, rz = float(pos[0]), float(pos[1]), float(pos[2])
            dist = ((x - rx) ** 2 + (y - ry) ** 2 + (z - rz) ** 2) ** 0.5
            if dist < tolerance:
                return {"id": rid, "type": r.get("type"), "position": pos}
    return None


def get_all_robots_positions() -> List[Dict[str, Any]]:
    """Return positions of all robots. Shared helper for collision awareness."""
    with _lock:
        robots = _state.get("robots", [])
        return [
            {"id": r.get("id"), "type": r.get("type"), "position": list(r.get("position") or [0, 0, 0])}
            for r in robots
        ]

