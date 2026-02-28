import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from chess.state_store import get_state
from chess.commands import execute_chess_command
from chess.ai_agent import choose_ai_move, root_chess_ai_agent

load_dotenv()

MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)

APP_NAME = os.getenv("AGENTS_APP_NAME", "talk_chess")
_ai_session_service = InMemorySessionService()
_known_ai_sessions: set[str] = set()
_ai_runner = Runner(
    agent=root_chess_ai_agent,
    app_name=APP_NAME,
    session_service=_ai_session_service,
)


def _session_id_from_context(tool_context: ToolContext) -> str:
    return (
        getattr(tool_context, "session_id", None)
        or getattr(getattr(tool_context, "session", None), "id", None)
        or "default"
    )


async def _ensure_ai_session_async(user_id: str, session_id: str) -> None:
    key = f"{user_id}:{session_id}"
    if key in _known_ai_sessions:
        return
    await _ai_session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    _known_ai_sessions.add(key)


async def _run_ai_subagent_message_async(session_id: str, message: str) -> str:
    await _ensure_ai_session_async(user_id=session_id, session_id=session_id)
    content = types.Content(role="user", parts=[types.Part(text=message)])
    events = _ai_runner.run_async(
        user_id=session_id,
        session_id=session_id,
        new_message=content,
    )

    final_text_parts: list[str] = []
    async for event in events:
        if getattr(event, "is_final_response", None) and event.is_final_response() and event.content:
            for p in event.content.parts:
                text = getattr(p, "text", None)
                if text:
                    final_text_parts.append(str(text))
    if not final_text_parts:
        raise RuntimeError("Chess AI sub-agent returned empty response")
    return " ".join(" ".join(final_text_parts).split())


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


async def call_chess_ai(tool_context: ToolContext, side: str = "black") -> Dict[str, Any]:
    """Choose one legal AI move for side via sub-agent; does not apply it."""
    side_key = (side or "black").strip().lower()
    if side_key not in {"white", "black"}:
        return {
            "success": False,
            "error": "side must be white or black",
            "verified_fact": "side must be white or black",
        }
    session_id = _session_id_from_context(tool_context)
    # Invoke dedicated AI agent for planning text-level suggestion.
    try:
        ai_reply = await _run_ai_subagent_message_async(
            session_id=session_id,
            message=f"Choose a legal move for {side_key}.",
        )
    except Exception as exc:
        return {
            "success": False,
            "error": f"AI planner failed: {exc}",
            "verified_fact": f"AI planner failed: {exc}",
        }
    # Deterministic move payload still comes from command helper.
    choice = choose_ai_move(side=side_key)
    if not choice.get("success"):
        err = choice.get("error") or f"No legal moves for {side_key}."
        return {"success": False, "error": err, "verified_fact": err}
    return {
        "success": True,
        "verified_fact": choice["verified_fact"],
        "ai_reply": ai_reply,
        "from_square": choice["from_square"],
        "to_square": choice["to_square"],
        "piece": choice["piece"],
        "side": side_key,
    }


def _is_ai_turn(state: Dict[str, Any]) -> bool:
    mode = state.get("mode")
    status = state.get("status", "in_progress")
    turn = state.get("turn")
    human_side = state.get("human_side", "white")
    if mode != "human_vs_ai" or status != "in_progress":
        return False
    if turn not in {"white", "black"} or human_side not in {"white", "black"}:
        return False
    return turn != human_side


def _apply_ai_move_if_needed(state: Dict[str, Any]) -> Dict[str, Any]:
    """If it's AI turn in human_vs_ai mode, apply exactly one legal AI move."""
    if not _is_ai_turn(state):
        return {
            "applied": False,
            "reply": "",
            "chess_state": state,
        }

    ai_side = state.get("turn", "black")
    ai = choose_ai_move(side=ai_side)
    if not ai.get("success"):
        msg = ai.get("error") or f"No legal moves for {ai_side}."
        return {
            "applied": False,
            "reply": msg,
            "chess_state": state,
            "error": msg,
        }

    out = execute_chess_command(
        "move",
        from_square=ai["from_square"],
        to_square=ai["to_square"],
        side=ai_side,
    )
    return {
        "applied": True,
        "reply": out["reply"],
        "chess_state": out["chess_state"],
    }


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
    state_before = get_state()
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

        if (
            action == "move"
            and state_before.get("mode") == "human_vs_ai"
            and state_before.get("turn") != state_before.get("human_side")
        ):
            err = "It is AI's turn. The AI will move first."
            return {"success": False, "error": err, "verified_fact": err, "chess_state": state_before}

        out = execute_chess_command(
            parsed["action"],
            from_square=parsed.get("from_square"),
            to_square=parsed.get("to_square"),
            mode=parsed.get("mode"),
            human_side=parsed.get("human_side"),
        )
        latest_state = out["chess_state"]
        ai_followup = _apply_ai_move_if_needed(latest_state)
        if ai_followup.get("applied"):
            combined = f"{out['reply']} AI moved: {ai_followup['reply']}"
            return {
                "success": True,
                "verified_fact": combined,
                "chess_state": ai_followup["chess_state"],
            }
        if ai_followup.get("error"):
            combined = f"{out['reply']} AI could not move: {ai_followup['error']}"
            return {
                "success": True,
                "verified_fact": combined,
                "chess_state": ai_followup["chess_state"],
            }
        return {"success": True, "verified_fact": out["reply"], "chess_state": latest_state}
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

