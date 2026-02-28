import re
from typing import Any, Dict, Optional


_ID_RE = r"([a-z0-9._-]+)"
_NUM_RE = r"(-?\d+(?:\.\d+)?)"


def normalize_robot(token: str) -> Optional[str]:
    t = (token or "").strip().lower()
    if t in ("ugv", "ugv-1", "ugx", "ugx-1", "agv", "agv-1"):
        return "ugv"
    if t in ("uav", "uav-1"):
        return "uav"
    if t in ("arm", "arm-1"):
        return "arm"
    return None


def parse_direct_warehouse_command(message: str) -> Optional[Dict[str, Any]]:
    """
    Parse deterministic warehouse commands from free text.
    Returns kwargs for execute_warehouse_command(...) or None.
    """
    msg = re.sub(r"\s+", " ", (message or "").strip().lower())
    msg = re.sub(r"^(please|kindly)\s+", "", msg)
    msg = re.sub(r"[.!?]+$", "", msg)
    if not msg:
        return None

    # Keep these on LLM/sub-agent path.
    if "toward" in msg or "towards" in msg:
        return None
    if any(k in msg for k in ("scan", "mapping", "map ", "find items", "find item")):
        return None

    # move patterns
    m = re.match(
        r"^(?:move\s+)?(?:the\s+)?(ugv|ugx|agv|uav|arm)(?:\s+move(?:\s+to)?|\s+to)?\s+(north|south|east|west)$",
        msg,
    )
    if m:
        robot = normalize_robot(m.group(1))
        if robot:
            return {"robot": robot, "action": "move", "direction": m.group(2)}

    m = re.match(r"^move\s+(north|south|east|west)\s+(?:the\s+)?(ugv|ugx|agv|uav|arm)$", msg)
    if m:
        robot = normalize_robot(m.group(2))
        if robot:
            return {"robot": robot, "action": "move", "direction": m.group(1)}

    # absolute move coordinates (x z or x y z)
    m = re.match(
        rf"^(?:move\s+)?(?:the\s+)?(ugv|ugx|agv|uav|arm)(?:\s+move)?\s+to\s+{_NUM_RE}\s+{_NUM_RE}(?:\s+{_NUM_RE})?$",
        msg,
    )
    if m:
        robot = normalize_robot(m.group(1))
        if robot:
            x_val = float(m.group(2))
            z_or_y = float(m.group(3))
            third = m.group(4)
            if third is None:
                return {"robot": robot, "action": "move", "x": x_val, "z": z_or_y}
            return {"robot": robot, "action": "move", "x": x_val, "y": z_or_y, "z": float(third)}

    # arm stack operations
    m = re.match(rf"^arm\s+(?:pick|grab|take|get)\s+(?:from\s+)?(?:stack\s+)?{_ID_RE}$", msg)
    if m:
        return {"robot": "arm", "action": "pick_from_stack", "stack_id": m.group(1)}
    m = re.match(rf"^(?:pick|grab|take|get)\s+from\s+stack\s+{_ID_RE}$", msg)
    if m:
        return {"robot": "arm", "action": "pick_from_stack", "stack_id": m.group(1)}

    m = re.match(
        rf"^(?:arm\s+)?(?:place|put|stack|add)\s+{_ID_RE}\s+(?:on|onto|to)\s+stack\s+{_ID_RE}$",
        msg,
    )
    if m:
        return {"robot": "arm", "action": "place_on_stack", "item_id": m.group(1), "stack_id": m.group(2)}

    # UGV drop: infer ugv when robot omitted
    m = re.match(
        rf"^(?:(?:ugv|ugx)\s+)?(?:drop|place|put|release)\s+{_ID_RE}\s+(?:at|to)?\s*\(?\s*{_NUM_RE}\s*[, ]\s*{_NUM_RE}\s*\)?$",
        msg,
    )
    if m:
        return {
            "robot": "ugv",
            "action": "drop",
            "item_id": m.group(1),
            "x": float(m.group(2)),
            "z": float(m.group(3)),
        }

    # UGV pick: infer ugv when robot omitted
    # Avoid matching stack commands.
    if "stack" not in msg:
        m = re.match(
            rf"^(?:(?:ugv|ugx)\s+)?(?:move\s+)?(?:pick|grab|collect|take|get)(?:\s+up)?\s+(?:item\s+)?{_ID_RE}$",
            msg,
        )
        if m:
            return {"robot": "ugv", "action": "pick", "item_id": m.group(1)}

    return None


def looks_like_direct_robot_command(message: str) -> bool:
    """Detect movement/manipulation intents that must not fall back to free-form LLM replies."""
    msg = re.sub(r"\s+", " ", (message or "").strip().lower())
    if not msg:
        return False
    has_robot = re.search(r"\b(ugv|ugx|agv|uav|arm)\b", msg) is not None
    has_action = re.search(
        r"\b(move|north|south|east|west|pick|drop|place|put|stack|grab|collect|take|get|release)\b",
        msg,
    ) is not None
    return bool(has_robot and has_action)
