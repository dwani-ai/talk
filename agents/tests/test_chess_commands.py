import os
import sys


AGENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if AGENTS_DIR not in sys.path:
    sys.path.insert(0, AGENTS_DIR)

from chess import state_store
from chess.commands import execute_chess_command, verify_chess_state_after_command


def _reset(mode: str = "human_vs_ai", human_side: str = "white"):
    state_store.reset_state(mode=mode, human_side=human_side)


def test_new_game_defaults_and_turn():
    _reset()
    out = execute_chess_command("new_game")
    state = out["chess_state"]
    assert state["turn"] == "white"
    assert len(state["board"]) == 32
    assert "Started a new chess game" in out["reply"]


def test_move_turn_flip_and_verify():
    _reset()
    before = state_store.get_state()
    out = execute_chess_command("move", from_square="e2", to_square="e4")
    after = state_store.get_state()
    assert after["board"].get("e4") == "wP"
    assert "e2->e4" in out["reply"]
    ok, reason = verify_chess_state_after_command(
        "move",
        before,
        after,
        from_square="e2",
        to_square="e4",
    )
    assert ok, reason
    assert after["turn"] == "black"


def test_capture_sequence():
    _reset(mode="human_vs_human")
    execute_chess_command("move", from_square="e2", to_square="e4")
    execute_chess_command("move", from_square="d7", to_square="d5")
    out = execute_chess_command("move", from_square="e4", to_square="d5")
    state = state_store.get_state()
    assert state["board"].get("d5") == "wP"
    assert "captured bP" in out["reply"]


def test_invalid_move_rejected():
    _reset()
    try:
        execute_chess_command("move", from_square="e2", to_square="e5")
    except ValueError as exc:
        assert "Illegal pawn move" in str(exc)
    else:
        raise AssertionError("Expected ValueError for illegal pawn move")

