import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from chess.state_store import get_state
from chess.commands import execute_chess_command
from chess.ai_agent import choose_ai_move

load_dotenv()

MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


def _parse_square_move(message: str) -> Optional[Dict[str, str]]:
    text = (message or "").strip().lower()
    match = re.search(r"\b([a-h][1-8])\s*(?:to|->|-|\s)\s*([a-h][1-8])\b", text)
    if match:
        return {"from_square": match.group(1), "to_square": match.group(2)}
    compact = re.search(r"\b([a-h][1-8])([a-h][1-8])\b", text)
    if compact:
        return {"from_square": compact.group(1), "to_square": compact.group(2)}
    verbose = re.search(r"\bfrom\s+([a-h][1-8])\s+to\s+([a-h][1-8])\b", text)
    if verbose:
        return {"from_square": verbose.group(1), "to_square": verbose.group(2)}
    return None


def _parse_semantic_pawn_move(message: str) -> Optional[Dict[str, str]]:
    text = (message or "").strip().lower()
    mentions_king_pawn = (
        "pawn in front of king" in text
        or "king pawn" in text
        or "pawn before king" in text
    )
    if not mentions_king_pawn:
        return None

    two_squares = any(
        token in text
        for token in ["two places", "two squares", "2 places", "2 squares", "double step"]
    )
    one_square = any(token in text for token in ["one place", "one square", "1 place", "1 square"])

    state = get_state()
    turn = state.get("turn", "white")
    if turn == "white":
        from_sq = "e2"
        to_sq = "e4" if two_squares else "e3"
    else:
        from_sq = "e7"
        to_sq = "e5" if two_squares else "e6"

    # Default to the common opening intent (two-square king pawn) when ambiguous.
    if not two_squares and not one_square:
        to_sq = "e4" if turn == "white" else "e5"

    return {"from_square": from_sq, "to_square": to_sq}


def _parse_user_command(message: str) -> Dict[str, Any]:
    text = (message or "").strip().lower()

    if any(k in text for k in ["new game", "reset", "start game", "start new game"]):
        mode = "human_vs_ai"
        if "human vs human" in text or "hvh" in text:
            mode = "human_vs_human"
        human_side = "white"
        if "as black" in text:
            human_side = "black"
        return {"action": "new_game", "mode": mode, "human_side": human_side}

    if "state" in text or "board" in text or "whose turn" in text:
        return {"action": "get_state"}

    if "ai move" in text or "computer move" in text or "bot move" in text:
        return {"action": "ai_move"}

    semantic_move = _parse_semantic_pawn_move(text)
    if semantic_move:
        return {"action": "move", **semantic_move}

    move = _parse_square_move(text)
    if move:
        return {"action": "move", **move}

    raise ValueError(
        "Unsupported command. Try: 'new game', 'e2 to e4', 'ai move', or 'show board state'."
    )


def call_chess_ai(tool_context: ToolContext, side: str = "black") -> Dict[str, Any]:
    """Choose one legal AI move for side; does not apply it."""
    return choose_ai_move(side=side)


def get_chess_state(tool_context: ToolContext) -> Dict[str, Any]:
    """Return the complete chess state snapshot."""
    state = get_state()
    return {
        "success": True,
        "verified_fact": f"Current turn: {state.get('turn')}.",
        "chess_state": state,
    }


def run_chess_command(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Parse user message and deterministically apply chess command."""
    try:
        parsed = _parse_user_command(message)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "verified_fact": str(exc)}

    action = parsed["action"]
    try:
        if action == "ai_move":
            state = get_state()
            ai_side = state.get("turn", "black")
            ai = choose_ai_move(side=ai_side)
            if not ai.get("success"):
                err = ai.get("error") or "AI could not find a legal move."
                return {"success": False, "error": err, "verified_fact": err}
            out = execute_chess_command(
                "move",
                from_square=ai["from_square"],
                to_square=ai["to_square"],
                side=ai_side,
            )
            return {
                "success": True,
                "verified_fact": out["reply"],
                "chess_state": out["chess_state"],
            }

        out = execute_chess_command(
            parsed["action"],
            from_square=parsed.get("from_square"),
            to_square=parsed.get("to_square"),
            mode=parsed.get("mode"),
            human_side=parsed.get("human_side"),
        )
        return {"success": True, "verified_fact": out["reply"], "chess_state": out["chess_state"]}
    except ValueError as exc:
        err = str(exc)
        return {"success": False, "error": err, "verified_fact": f"Command failed: {err}"}


CHESS_ORCHESTRATOR_INSTRUCTION = """
You are the chess orchestrator for Talk Chess.
You must always call exactly one tool before replying.

Use run_chess_command for user command execution:
- new game / reset / mode change
- move commands like "e2 to e4" or "e2e4"
- ai move
- board/state requests

Use get_chess_state when user asks to inspect board details without changing anything.
Use call_chess_ai only when the user explicitly asks for a move suggestion and not execution.

Validation rule (no hallucination):
- Reply only from tool output.
- If success=true, reply with verified_fact only.
- If success=false, reply with the returned error/verified_fact only.
Do not invent moves, captures, or board positions.
"""


root_chess_orchestrator_agent = Agent(
    name="chess_orchestrator",
    model=MODEL,
    description="Agent-driven chess gameplay with deterministic move execution.",
    instruction=CHESS_ORCHESTRATOR_INSTRUCTION,
    tools=[run_chess_command, get_chess_state, call_chess_ai],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.15,
    ),
)

