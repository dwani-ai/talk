import os
import sys


AGENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)

from warehouse import state_store
from warehouse.commands import execute_warehouse_command, verify_warehouse_state_after_command


def _reset_state():
    state_store._init_default_state()


def test_verify_move_direction_and_pick_drop_sequence():
    _reset_state()

    before = state_store.get_state()
    out = execute_warehouse_command("ugv", "move", direction="north")
    assert "ugv-1 moved to" in out["reply"]
    after = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "ugv",
        "move",
        after,
        prev_state=before,
        direction="north",
    )
    assert ok, reason

    before_pick = state_store.get_state()
    out_pick = execute_warehouse_command("ugv", "pick", item_id="item-1")
    assert "picked item-1" in out_pick["reply"]
    after_pick = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "ugv",
        "pick",
        after_pick,
        prev_state=before_pick,
        item_id="item-1",
    )
    assert ok, reason

    before_drop = state_store.get_state()
    out_drop = execute_warehouse_command("ugv", "drop", item_id="item-1", x=10, z=5)
    assert "dropped item-1" in out_drop["reply"]
    after_drop = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "ugv",
        "drop",
        after_drop,
        prev_state=before_drop,
        item_id="item-1",
        x=10,
        z=5,
    )
    assert ok, reason


def test_verify_stack_pick_and_place():
    _reset_state()

    before_pick = state_store.get_state()
    out_pick = execute_warehouse_command("arm", "pick_from_stack", stack_id="stack-1")
    assert "picked item-3 from stack-1" in out_pick["reply"]
    after_pick = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "arm",
        "pick_from_stack",
        after_pick,
        prev_state=before_pick,
        stack_id="stack-1",
    )
    assert ok, reason

    before_place = state_store.get_state()
    out_place = execute_warehouse_command("arm", "place_on_stack", stack_id="stack-1", item_id="item-3")
    assert "placed item-3 on stack-1" in out_place["reply"]
    after_place = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "arm",
        "place_on_stack",
        after_place,
        prev_state=before_place,
        stack_id="stack-1",
        item_id="item-3",
    )
    assert ok, reason


def test_invalid_direction_rejected():
    _reset_state()
    try:
        execute_warehouse_command("uav", "move", direction="up")
    except ValueError as e:
        assert "direction must be one of" in str(e)
    else:
        raise AssertionError("Expected ValueError for invalid direction")


def test_integration_sequence_move_ugv_then_uav():
    _reset_state()

    before_ugv = state_store.get_state()
    execute_warehouse_command("ugv", "move", direction="north")
    after_ugv = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "ugv",
        "move",
        after_ugv,
        prev_state=before_ugv,
        direction="north",
    )
    assert ok, reason

    before_uav = state_store.get_state()
    execute_warehouse_command("uav", "move", direction="south")
    after_uav = state_store.get_state()
    ok, reason = verify_warehouse_state_after_command(
        "uav",
        "move",
        after_uav,
        prev_state=before_uav,
        direction="south",
    )
    assert ok, reason
