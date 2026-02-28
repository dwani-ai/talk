import os
import sys


AGENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)

from warehouse.direct_commands import parse_direct_warehouse_command, looks_like_direct_robot_command


def test_parse_move_variants():
    assert parse_direct_warehouse_command("move uav south") == {
        "robot": "uav",
        "action": "move",
        "direction": "south",
    }
    assert parse_direct_warehouse_command("move the ugv north") == {
        "robot": "ugv",
        "action": "move",
        "direction": "north",
    }
    assert parse_direct_warehouse_command("move south ugx") == {
        "robot": "ugv",
        "action": "move",
        "direction": "south",
    }
    assert parse_direct_warehouse_command("move agv to south") == {
        "robot": "ugv",
        "action": "move",
        "direction": "south",
    }
    assert parse_direct_warehouse_command("move uav to north") == {
        "robot": "uav",
        "action": "move",
        "direction": "north",
    }


def test_parse_pick_drop_and_stack_variants():
    assert parse_direct_warehouse_command("pick up item-1") == {
        "robot": "ugv",
        "action": "pick",
        "item_id": "item-1",
    }
    assert parse_direct_warehouse_command("put item-1 at 10 5") == {
        "robot": "ugv",
        "action": "drop",
        "item_id": "item-1",
        "x": 10.0,
        "z": 5.0,
    }
    assert parse_direct_warehouse_command("arm pick stack-1") == {
        "robot": "arm",
        "action": "pick_from_stack",
        "stack_id": "stack-1",
    }
    assert parse_direct_warehouse_command("put item-3 on stack stack-1") == {
        "robot": "arm",
        "action": "place_on_stack",
        "item_id": "item-3",
        "stack_id": "stack-1",
    }


def test_parse_ambiguous_or_subagent_intents_return_none():
    assert parse_direct_warehouse_command("move towards arm") is None
    assert parse_direct_warehouse_command("scan the area") is None


def test_detect_direct_robot_command_intent():
    assert looks_like_direct_robot_command("move agv to south")
    assert looks_like_direct_robot_command("uav north")
    assert not looks_like_direct_robot_command("scan the north section")
