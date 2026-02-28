from typing import Any, Dict, List, Optional, Tuple

try:
    from .state_store import get_state, reset_state, apply_move, FILES, RANKS
except ImportError:
    from state_store import get_state, reset_state, apply_move, FILES, RANKS  # type: ignore[import-not-found]


def _is_square(sq: str) -> bool:
    return isinstance(sq, str) and len(sq) == 2 and sq[0] in FILES and sq[1] in RANKS


def _coords(square: str) -> Tuple[int, int]:
    return FILES.index(square[0]), int(square[1]) - 1


def _square(x: int, y: int) -> str:
    return f"{FILES[x]}{y + 1}"


def _piece_color(piece: str) -> str:
    return "white" if piece.startswith("w") else "black"


def _piece_kind(piece: str) -> str:
    return piece[1]


def _opponent(side: str) -> str:
    return "black" if side == "white" else "white"


def _inside(x: int, y: int) -> bool:
    return 0 <= x < 8 and 0 <= y < 8


def _piece_at(board: Dict[str, str], x: int, y: int) -> Optional[str]:
    if not _inside(x, y):
        return None
    return board.get(_square(x, y))


def _path_clear(board: Dict[str, str], x0: int, y0: int, x1: int, y1: int) -> bool:
    dx = 0 if x1 == x0 else (1 if x1 > x0 else -1)
    dy = 0 if y1 == y0 else (1 if y1 > y0 else -1)
    cx, cy = x0 + dx, y0 + dy
    while (cx, cy) != (x1, y1):
        if _piece_at(board, cx, cy) is not None:
            return False
        cx += dx
        cy += dy
    return True


def _is_legal_move_for_piece(board: Dict[str, str], from_sq: str, to_sq: str, side: str) -> Tuple[bool, str]:
    piece = board.get(from_sq)
    if not piece:
        return False, f"No piece at {from_sq}."
    if _piece_color(piece) != side:
        return False, f"Piece at {from_sq} belongs to {_piece_color(piece)}."
    if from_sq == to_sq:
        return False, "from and to squares must differ."
    target = board.get(to_sq)
    if target and _piece_color(target) == side:
        return False, f"Destination {to_sq} occupied by your own piece."

    x0, y0 = _coords(from_sq)
    x1, y1 = _coords(to_sq)
    dx, dy = x1 - x0, y1 - y0
    adx, ady = abs(dx), abs(dy)
    kind = _piece_kind(piece)

    if kind == "P":
        dir_y = 1 if side == "white" else -1
        start_rank = 1 if side == "white" else 6
        # forward one
        if dx == 0 and dy == dir_y and target is None:
            return True, ""
        # forward two from start
        if dx == 0 and dy == 2 * dir_y and y0 == start_rank and target is None:
            between = _piece_at(board, x0, y0 + dir_y)
            if between is None:
                return True, ""
        # capture
        if adx == 1 and dy == dir_y and target is not None and _piece_color(target) != side:
            return True, ""
        return False, "Illegal pawn move."

    if kind == "N":
        if (adx, ady) in {(1, 2), (2, 1)}:
            return True, ""
        return False, "Illegal knight move."

    if kind == "B":
        if adx == ady and _path_clear(board, x0, y0, x1, y1):
            return True, ""
        return False, "Illegal bishop move."

    if kind == "R":
        if (dx == 0 or dy == 0) and _path_clear(board, x0, y0, x1, y1):
            return True, ""
        return False, "Illegal rook move."

    if kind == "Q":
        if ((adx == ady) or (dx == 0 or dy == 0)) and _path_clear(board, x0, y0, x1, y1):
            return True, ""
        return False, "Illegal queen move."

    if kind == "K":
        if max(adx, ady) == 1:
            return True, ""
        return False, "Illegal king move."

    return False, f"Unsupported piece kind '{kind}'."


def list_legal_moves_for_side(state: Dict[str, Any], side: str) -> List[Dict[str, str]]:
    board: Dict[str, str] = state.get("board", {})
    out: List[Dict[str, str]] = []
    for from_sq, piece in board.items():
        if _piece_color(piece) != side:
            continue
        for f in FILES:
            for r in RANKS:
                to_sq = f"{f}{r}"
                ok, _ = _is_legal_move_for_piece(board, from_sq, to_sq, side)
                if ok:
                    out.append({"from": from_sq, "to": to_sq, "piece": piece})
    return out


def verify_chess_state_after_command(
    action: str,
    prev_state: Dict[str, Any],
    new_state: Dict[str, Any],
    *,
    from_square: Optional[str] = None,
    to_square: Optional[str] = None,
) -> Tuple[bool, str]:
    action = (action or "").strip().lower()
    if action == "new_game":
        if new_state.get("turn") != "white":
            return False, "new game should start with white turn"
        if len((new_state.get("board") or {}).keys()) != 32:
            return False, "new game board should have 32 pieces"
        return True, ""

    if action == "move":
        if not from_square or not to_square:
            return False, "missing from/to for move verification"
        prev_board = prev_state.get("board", {})
        new_board = new_state.get("board", {})
        moved_piece = prev_board.get(from_square)
        if moved_piece is None:
            return False, f"no piece at {from_square} before move"
        if from_square in new_board:
            return False, f"piece still at {from_square} after move"
        if new_board.get(to_square) is None:
            return False, f"no piece at {to_square} after move"
        expected_turn = _opponent(prev_state.get("turn", "white"))
        if new_state.get("turn") != expected_turn:
            return False, "turn did not flip after move"
        return True, ""

    return True, ""


def execute_chess_command(
    action: str,
    *,
    from_square: Optional[str] = None,
    to_square: Optional[str] = None,
    mode: Optional[str] = None,
    human_side: Optional[str] = None,
    side: Optional[str] = None,
    promotion: Optional[str] = None,
) -> Dict[str, Any]:
    action_key = (action or "").strip().lower()

    if action_key == "new_game":
        mode_val = mode if mode in {"human_vs_ai", "human_vs_human"} else "human_vs_ai"
        human_side_val = human_side if human_side in {"white", "black"} else "white"
        state = reset_state(mode=mode_val, human_side=human_side_val)
        return {
            "reply": f"Started a new chess game in {mode_val} mode. White to move.",
            "chess_state": state,
        }

    if action_key == "get_state":
        state = get_state()
        return {
            "reply": f"Current turn: {state.get('turn')}.",
            "chess_state": state,
        }

    if action_key != "move":
        raise ValueError("action must be one of: new_game, move, get_state")

    if not from_square or not to_square:
        raise ValueError("from_square and to_square are required for move.")
    from_sq = from_square.strip().lower()
    to_sq = to_square.strip().lower()
    if not _is_square(from_sq) or not _is_square(to_sq):
        raise ValueError("Squares must be algebraic notation like e2, e4.")

    prev = get_state()
    board: Dict[str, str] = prev.get("board", {})
    turn = prev.get("turn", "white")
    mover_side = side if side in {"white", "black"} else turn
    if mover_side != turn:
        raise ValueError(f"It is {turn}'s turn, not {mover_side}'s.")
    piece = board.get(from_sq)
    if not piece:
        raise ValueError(f"No piece at {from_sq}.")

    ok, reason = _is_legal_move_for_piece(board, from_sq, to_sq, mover_side)
    if not ok:
        raise ValueError(reason)

    target_piece = board.get(to_sq)
    next_state = apply_move(
        from_square=from_sq,
        to_square=to_sq,
        promotion=promotion,
        moved_piece=piece,
        captured_piece=target_piece,
    )

    # Simple game-over check for v1 core rules: king captured.
    board_after = next_state.get("board", {})
    white_king_alive = any(p == "wK" for p in board_after.values())
    black_king_alive = any(p == "bK" for p in board_after.values())
    if not white_king_alive:
        next_state["status"] = "finished"
        next_state["winner"] = "black"
    elif not black_king_alive:
        next_state["status"] = "finished"
        next_state["winner"] = "white"

    verified, reason = verify_chess_state_after_command(
        "move", prev, next_state, from_square=from_sq, to_square=to_sq
    )
    if not verified:
        raise ValueError(f"state verification failed: {reason}")

    capture_suffix = f", captured {target_piece}" if target_piece else ""
    reply = f"{piece} moved {from_sq}->{to_sq}{capture_suffix}. {next_state.get('turn')} to move."
    return {"reply": reply, "chess_state": next_state}

