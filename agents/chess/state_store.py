import sys
import threading
from copy import deepcopy
from typing import Any, Dict, List, Optional

_this_module = sys.modules[__name__]
sys.modules.setdefault("chess.state_store", _this_module)

_lock = threading.Lock()

FILES = "abcdefgh"
RANKS = "12345678"


def _initial_board() -> Dict[str, str]:
    board: Dict[str, str] = {}
    # White major pieces
    board.update(
        {
            "a1": "wR",
            "b1": "wN",
            "c1": "wB",
            "d1": "wQ",
            "e1": "wK",
            "f1": "wB",
            "g1": "wN",
            "h1": "wR",
        }
    )
    # White pawns
    for f in FILES:
        board[f"{f}2"] = "wP"
    # Black major pieces
    board.update(
        {
            "a8": "bR",
            "b8": "bN",
            "c8": "bB",
            "d8": "bQ",
            "e8": "bK",
            "f8": "bB",
            "g8": "bN",
            "h8": "bR",
        }
    )
    # Black pawns
    for f in FILES:
        board[f"{f}7"] = "bP"
    return board


_state: Dict[str, Any] = {}


def _init_default_state() -> None:
    with _lock:
        _state.clear()
        _state.update(
            {
                "board": _initial_board(),
                "turn": "white",
                "mode": "human_vs_ai",
                "human_side": "white",
                "status": "in_progress",
                "winner": None,
                "result": None,
                "move_history": [],
                "last_move": None,
                "captured_white": [],
                "captured_black": [],
                "castling_rights": {
                    "white": {"king_side": True, "queen_side": True},
                    "black": {"king_side": True, "queen_side": True},
                },
                "en_passant_target": None,
                "halfmove_clock": 0,
                "fullmove_number": 1,
                "position_counts": {},
            }
        )


_init_default_state()


def get_state() -> Dict[str, Any]:
    with _lock:
        return deepcopy(_state)


def set_state(new_state: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        _state.clear()
        _state.update(deepcopy(new_state))
        return deepcopy(_state)


def reset_state(mode: str = "human_vs_ai", human_side: str = "white") -> Dict[str, Any]:
    _init_default_state()
    with _lock:
        _state["mode"] = mode
        _state["human_side"] = human_side
        return deepcopy(_state)


def apply_move(
    *,
    from_square: str,
    to_square: str,
    promotion: Optional[str],
    moved_piece: str,
    captured_piece: Optional[str],
) -> Dict[str, Any]:
    with _lock:
        board: Dict[str, str] = _state["board"]
        board.pop(from_square, None)
        if promotion and moved_piece[1] == "P":
            board[to_square] = f"{moved_piece[0]}{promotion.upper()}"
        else:
            board[to_square] = moved_piece

        if captured_piece:
            if captured_piece.startswith("w"):
                _state["captured_white"].append(captured_piece)
            else:
                _state["captured_black"].append(captured_piece)

        _state["last_move"] = {"from": from_square, "to": to_square, "piece": moved_piece}
        _state["move_history"].append(
            {
                "from": from_square,
                "to": to_square,
                "piece": moved_piece,
                "captured": captured_piece,
                "promotion": promotion,
            }
        )
        _state["turn"] = "black" if _state["turn"] == "white" else "white"
        return deepcopy(_state)

