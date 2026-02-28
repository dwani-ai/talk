"""
Deterministic warehouse command execution. Used by the HTTP API and by agents.
Raises ValueError with a message on validation failure; returns {reply, robots, items} on success.
"""
from typing import Any, Dict, Optional

try:
    from .state_store import (
        get_state,
        get_warehouse_bounds,
        is_within_bounds,
        position_occupied_by_other,
        update_robot_position,
        update_robot_status,
        upsert_item,
    )
except ImportError:
    from state_store import (  # type: ignore[import-not-found]
        get_state,
        get_warehouse_bounds,
        is_within_bounds,
        position_occupied_by_other,
        update_robot_position,
        update_robot_status,
        upsert_item,
    )


def _get_robot_position(state: Dict[str, Any], robot_id: str) -> tuple[float, float, float]:
    robots = state.get("robots", [])
    r = next((x for x in robots if x.get("id") == robot_id), None) or {}
    pos = r.get("position") or [0.0, 0.0, 0.0]
    return float(pos[0]), float(pos[1]), float(pos[2])


def _get_item_position(state: Dict[str, Any], item_id: str) -> Optional[tuple[float, float, float]]:
    items = state.get("items", [])
    it = next((x for x in items if x.get("id") == item_id), None)
    if not it:
        return None
    pos = it.get("position") or [0.0, 0.0, 0.0]
    return float(pos[0]), float(pos[1]), float(pos[2])


def _stack_height(state: Dict[str, Any], stack_id: str) -> int:
    items = state.get("items", [])
    return sum(1 for it in items if it.get("stack_id") == stack_id)


def _get_robot_carried_item(state: Dict[str, Any], robot_id: str) -> Optional[str]:
    robots = state.get("robots", [])
    r = next((x for x in robots if x.get("id") == robot_id), None) or {}
    task = r.get("current_task") or ""
    if task.startswith("carrying_"):
        return task.replace("carrying_", "").strip()
    if task.startswith("holding_"):
        return task.replace("holding_", "").strip()
    return None


def _get_robot_holding_item(state: Dict[str, Any], item_id: str) -> Optional[str]:
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


def _get_stack_base_position(state: Dict[str, Any], stack_id: str) -> tuple[float, float]:
    items = state.get("items", [])
    stack_items = [it for it in items if it.get("stack_id") == stack_id]
    if stack_items:
        pos = stack_items[0].get("position") or [25.0, 0.0, 10.0]
        return float(pos[0]), float(pos[2])
    return 25.0, 10.0


def execute_warehouse_command(
    robot: str,
    action: str = "move",
    direction: Optional[str] = None,
    item_id: Optional[str] = None,
    stack_id: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute a single warehouse command. Raises ValueError on validation error.
    Returns {"reply": str, "robots": list, "items": list}.
    """
    robot_key = robot.strip().lower()
    id_map = {"uav": "uav-1", "ugv": "ugv-1", "arm": "arm-1"}
    robot_id = id_map.get(robot_key)
    if not robot_id:
        raise ValueError("robot must be one of: uav, ugv, arm")

    state = get_state()
    cx, cy, cz = _get_robot_position(state, robot_id)
    reply: str
    action = (action or "").strip().lower() or "move"

    if action == "pick":
        if robot_key != "ugv":
            raise ValueError("Only UGV can pick items from the floor.")
        if not item_id:
            raise ValueError("item_id required for pick.")
        carried = _get_robot_carried_item(state, robot_id)
        if carried:
            raise ValueError(f"UGV is already carrying '{carried}'. Drop it first before picking another item.")
        item_id = item_id.strip()
        items = state.get("items", [])
        item = next((it for it in items if it.get("id") == item_id), None)
        if not item:
            raise ValueError(f"Item '{item_id}' not found.")
        if item.get("stack_id"):
            raise ValueError(f"Item '{item_id}' is on a stack. Use arm pick from stack.")
        held_by = _get_robot_holding_item(state, item_id)
        if held_by and held_by != robot_id:
            raise ValueError(f"Item '{item_id}' is already held by {held_by}. It must be released first.")
        ix, iy, iz = _get_item_position(state, item_id) or (0.0, 0.0, 0.0)
        update_robot_position(robot_id, ix, 0.0, iz)
        upsert_item(item_id, (ix, 0.0, iz), stack_id=None)
        update_robot_status(robot_id, "working", current_task=f"carrying_{item_id}")
        reply = f"{robot_id} moved to [{ix}, 0, {iz}], picked {item_id}."

    elif action == "drop":
        if robot_key != "ugv":
            raise ValueError("Only UGV can drop items.")
        if not item_id:
            raise ValueError("item_id required for drop.")
        if x is None or z is None:
            raise ValueError("x and z required for drop.")
        carried = _get_robot_carried_item(state, robot_id)
        item_id = item_id.strip()
        if carried != item_id:
            raise ValueError(
                f"UGV is not carrying '{item_id}'." + (f" (Currently carrying '{carried}')" if carried else "")
            )
        tx, tz = float(x), float(z)
        if not is_within_bounds(tx, 0.0, tz):
            w, d, _ = get_warehouse_bounds()
            raise ValueError(f"Drop position ({tx}, {tz}) is outside warehouse bounds (0–{w} x 0–{d}).")
        occupant = position_occupied_by_other(robot_id, tx, 0.0, tz)
        if occupant:
            raise ValueError(f"Cannot drop: {occupant['id']} is at ({tx}, {tz}). Choose another location.")
        update_robot_position(robot_id, tx, 0.0, tz)
        upsert_item(item_id, (tx, 0.0, tz), stack_id=None)
        update_robot_status(robot_id, "idle", current_task=None)
        reply = f"{robot_id} moved to [{tx}, 0, {tz}], dropped {item_id}."

    elif action == "pick_from_stack":
        if robot_key != "arm":
            raise ValueError("Only arm can pick from stack.")
        if not stack_id:
            raise ValueError("stack_id required for pick_from_stack.")
        holding = _get_robot_carried_item(state, robot_id)
        if holding:
            raise ValueError(f"Arm is already holding '{holding}'. Place it on a stack first before picking another.")
        stack_id = stack_id.strip()
        items = state.get("items", [])
        stack_items = [it for it in items if it.get("stack_id") == stack_id]
        if not stack_items:
            raise ValueError(f"No items in stack '{stack_id}'.")
        top = stack_items[-1]
        top_item_id = str(top.get("id"))
        ix, iy, iz = top.get("position") or [25.0, 0.0, 10.0]
        ix, iy, iz = float(ix), float(iy), float(iz)
        occupant = position_occupied_by_other(robot_id, ix, iy, iz)
        if occupant:
            raise ValueError(f"Cannot pick from stack: {occupant['id']} is at the stack. Ask it to move first.")
        update_robot_position(robot_id, ix, iy, iz)
        upsert_item(top_item_id, (ix, iy, iz), stack_id=None)
        update_robot_status(robot_id, "working", current_task=f"holding_{top_item_id}")
        reply = f"{robot_id} moved to [{ix}, {iy}, {iz}], picked {top_item_id} from {stack_id}."

    elif action == "place_on_stack":
        if robot_key != "arm":
            raise ValueError("Only arm can place on stack.")
        if not stack_id or not item_id:
            raise ValueError("stack_id and item_id required for place_on_stack.")
        holding = _get_robot_carried_item(state, robot_id)
        item_id = item_id.strip()
        if holding != item_id:
            raise ValueError(
                f"Arm is not holding '{item_id}'." + (f" (Currently holding '{holding}')" if holding else "")
            )
        stack_id = stack_id.strip()
        level = _stack_height(state, stack_id)
        base_x, base_z = _get_stack_base_position(state, stack_id)
        y_val = 0.5 * (level + 1)
        if not is_within_bounds(base_x, y_val, base_z):
            w, d, h = get_warehouse_bounds()
            raise ValueError(f"Stack position ({base_x}, {y_val}, {base_z}) would be outside warehouse bounds.")
        occupant = position_occupied_by_other(robot_id, base_x, y_val, base_z)
        if occupant:
            raise ValueError(f"Cannot place on stack: {occupant['id']} is at the stack. Ask it to move first.")
        update_robot_position(robot_id, base_x, y_val, base_z)
        upsert_item(item_id, (base_x, y_val, base_z), stack_id=stack_id)
        update_robot_status(robot_id, "idle", current_task=None)
        reply = f"{robot_id} moved to [{base_x}, {y_val}, {base_z}], placed {item_id} on {stack_id}."

    else:
        # move
        if x is not None and z is not None:
            tx = float(x)
            tz = float(z)
            ty = float(y) if y is not None else (0.0 if robot_key == "ugv" else (5.0 if robot_key == "uav" else cy))
        elif direction:
            direction = direction.strip().lower()
            step = 5.0
            dx = dz = 0.0
            if direction == "north":
                dz = -step
            elif direction == "south":
                dz = step
            elif direction == "east":
                dx = step
            elif direction == "west":
                dx = -step
            else:
                raise ValueError("direction must be one of: north, south, east, west")
            if robot_key == "uav":
                tx, ty, tz = cx + dx, 5.0, cz + dz
            elif robot_key == "ugv":
                tx, ty, tz = cx + dx, 0.0, cz + dz
            else:
                tx, ty, tz = cx + dx, cy, cz + dz
        else:
            raise ValueError("Provide direction or absolute coordinates (x,y,z) for move.")
        if not is_within_bounds(tx, ty, tz):
            w, d, h = get_warehouse_bounds()
            raise ValueError(f"Target position ({tx}, {ty}, {tz}) is outside warehouse bounds (0–{w} x 0–{d} x 0–{h}).")
        occupant = position_occupied_by_other(robot_id, tx, ty, tz)
        if occupant:
            raise ValueError(f"Would collide with {occupant['id']} at {occupant['position']}. Choose another position.")
        updated = update_robot_position(robot_id, tx, ty, tz)
        current = next((r for r in state.get("robots", []) if r.get("id") == robot_id), None) or {}
        task = current.get("current_task") or ""
        carried_id = None
        if task.startswith("carrying_"):
            carried_id = task.replace("carrying_", "").strip()
        elif task.startswith("holding_"):
            carried_id = task.replace("holding_", "").strip()
        if carried_id:
            if robot_key == "ugv":
                upsert_item(carried_id, (tx, 0.0, tz), stack_id=None)
            else:
                upsert_item(carried_id, (tx, ty, tz), stack_id=None)
            update_robot_status(robot_id, "working", current_task=task)
        else:
            update_robot_status(robot_id, "idle", current_task=None)
        reply = f"{robot_id} moved to [{updated['position'][0]}, {updated['position'][1]}, {updated['position'][2]}]."

    new_state = get_state()
    return {
        "reply": reply,
        "robots": new_state.get("robots", []),
        "items": new_state.get("items", []),
    }


def verify_warehouse_state_after_command(
    robot_key: str,
    action: str,
    state: Dict[str, Any],
    *,
    prev_state: Optional[Dict[str, Any]] = None,
    direction: Optional[str] = None,
    item_id: Optional[str] = None,
    stack_id: Optional[str] = None,
    x: Optional[float] = None,
    y: Optional[float] = None,
    z: Optional[float] = None,
) -> tuple[bool, str]:
    """
    Verify that warehouse state is consistent with the command having been applied.
    Returns (True, "") if verified; (False, reason) otherwise.
    """
    id_map = {"uav": "uav-1", "ugv": "ugv-1", "arm": "arm-1"}
    robot_id = id_map.get((robot_key or "").strip().lower())
    if not robot_id:
        return False, "unknown robot"
    robots = state.get("robots", [])
    items = state.get("items", [])
    r = next((x for x in robots if x.get("id") == robot_id), None)
    if not r:
        return False, f"robot {robot_id} not in state"
    pos = list(r.get("position") or [0, 0, 0])
    task = (r.get("current_task") or "") or ""

    action = (action or "move").strip().lower()

    prev_pos = None
    if isinstance(prev_state, dict):
        prev_r = next((x for x in prev_state.get("robots", []) if x.get("id") == robot_id), None)
        if prev_r:
            prev_pos = list(prev_r.get("position") or [0, 0, 0])

    if action == "move":
        if not is_within_bounds(pos[0], pos[1], pos[2]):
            return False, f"robot position {pos} out of bounds"
        if x is not None and z is not None:
            exp_x = float(x)
            exp_z = float(z)
            if y is not None:
                exp_y = float(y)
            else:
                if robot_id == "ugv-1":
                    exp_y = 0.0
                elif robot_id == "uav-1":
                    exp_y = 5.0
                else:
                    exp_y = float(prev_pos[1]) if prev_pos else float(pos[1])
            if abs(pos[0] - exp_x) > 0.01 or abs(pos[1] - exp_y) > 0.01 or abs(pos[2] - exp_z) > 0.01:
                return False, f"move target mismatch: expected [{exp_x}, {exp_y}, {exp_z}] got {pos}"
        if direction and prev_pos:
            step = 5.0
            dx = dz = 0.0
            d = direction.strip().lower()
            if d == "north":
                dz = -step
            elif d == "south":
                dz = step
            elif d == "east":
                dx = step
            elif d == "west":
                dx = -step
            exp_x = float(prev_pos[0]) + dx
            exp_z = float(prev_pos[2]) + dz
            exp_y = float(prev_pos[1]) if robot_id == "arm-1" else (0.0 if robot_id == "ugv-1" else 5.0)
            if abs(pos[0] - exp_x) > 0.01 or abs(pos[1] - exp_y) > 0.01 or abs(pos[2] - exp_z) > 0.01:
                return False, f"directional move mismatch: expected [{exp_x}, {exp_y}, {exp_z}] got {pos}"
        return True, ""

    if action == "pick":
        if not item_id:
            return True, ""
        if not task.startswith("carrying_"):
            return False, f"UGV not carrying after pick (current_task={task!r})"
        carried = task.replace("carrying_", "").strip()
        if carried != item_id:
            return False, f"UGV carrying {carried!r} not {item_id!r}"
        it = next((i for i in items if str(i.get("id")) == str(item_id)), None)
        if not it:
            return False, f"item {item_id} not in state"
        ipos = it.get("position") or [0, 0, 0]
        if abs(pos[0] - ipos[0]) > 0.01 or abs(pos[1] - ipos[1]) > 0.01 or abs(pos[2] - ipos[2]) > 0.01:
            return False, f"item position does not match robot position"
        if it.get("stack_id") is not None:
            return False, f"picked item {item_id} still has stack_id={it.get('stack_id')!r}"
        return True, ""

    if action == "drop":
        if item_id and task and task.startswith("carrying_"):
            return False, f"UGV still carrying after drop (current_task={task!r})"
        if item_id and x is not None and z is not None:
            it = next((i for i in items if str(i.get("id")) == str(item_id)), None)
            if not it:
                return False, f"item {item_id} not in state"
            ipos = it.get("position") or [0, 0, 0]
            if abs(float(ipos[1])) > 0.01:
                return False, f"dropped item must be on floor y=0, got {ipos[1]}"
            if it.get("stack_id") is not None:
                return False, f"dropped item should not be on stack, got stack_id={it.get('stack_id')!r}"
            if abs(ipos[0] - float(x)) > 0.01 or abs(ipos[2] - float(z)) > 0.01:
                return False, f"item not at drop position: expected ({x},0,{z}), got {ipos}"
        return True, ""

    if action == "pick_from_stack":
        if not task.startswith("holding_"):
            return False, f"Arm not holding after pick_from_stack (current_task={task!r})"
        held_id = task.replace("holding_", "").strip()
        it = next((i for i in items if str(i.get("id")) == held_id), None)
        if not it:
            return False, f"held item {held_id!r} not present in items"
        if it.get("stack_id") is not None:
            return False, f"held item {held_id!r} still has stack_id={it.get('stack_id')!r}"
        return True, ""

    if action == "place_on_stack":
        if item_id and stack_id:
            it = next((i for i in items if str(i.get("id")) == str(item_id)), None)
            if not it:
                return False, f"item {item_id} not in state"
            if it.get("stack_id") != stack_id:
                return False, f"item {item_id} not on stack {stack_id} after place"
            ipos = it.get("position") or [0, 0, 0]
            if float(ipos[1]) <= 0.0:
                return False, f"stacked item {item_id} should have y>0, got {ipos[1]}"
        if task and task.startswith("holding_"):
            return False, f"Arm still holding after place_on_stack (current_task={task!r})"
        return True, ""

    return True, ""
