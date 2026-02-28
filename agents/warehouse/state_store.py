import threading
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


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
    status: Optional[str] = None,
    current_task: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a robot entry in the state store."""
    with _lock:
        robots: List[Dict[str, Any]] = _state.setdefault("robots", [])
        idx = _find_robot_index(robot_id)
        if idx == -1:
            robot: Dict[str, Any] = {
                "id": robot_id,
                "type": robot_type or "unknown",
                "position": list(position) if position is not None else [0.0, 0.0, 0.0],
                "orientation": list(orientation) if orientation is not None else [0.0, 0.0, 0.0],
                "status": status or "idle",
                "current_task": current_task,
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
            if status is not None:
                robot["status"] = status
            if current_task is not None or current_task is None:
                # Allow explicitly clearing current_task by passing None.
                robot["current_task"] = current_task

        return deepcopy(robot)


def update_robot_position(robot_id: str, x: float, y: float, z: float) -> Dict[str, Any]:
    return upsert_robot(robot_id, position=(x, y, z))


def update_robot_status(robot_id: str, status: str, current_task: Optional[str] = None) -> Dict[str, Any]:
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

