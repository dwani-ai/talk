import os
import random
from typing import Any, Dict

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from chess.state_store import get_state
from chess.commands import list_legal_moves_for_side

load_dotenv()

MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


def choose_ai_move(side: str = "black") -> Dict[str, Any]:
    state = get_state()
    side_key = (side or "black").strip().lower()
    if side_key not in {"white", "black"}:
        return {"success": False, "error": "side must be white or black", "verified_fact": "side must be white or black"}
    legal = list_legal_moves_for_side(state, side_key)
    if not legal:
        return {"success": False, "error": f"no legal moves for {side_key}", "verified_fact": f"No legal moves for {side_key}."}
    move = random.choice(legal)
    return {
        "success": True,
        "verified_fact": f"AI proposes {move['from']}->{move['to']}",
        "from_square": move["from"],
        "to_square": move["to"],
        "piece": move["piece"],
        "side": side_key,
    }


def get_ai_move(tool_context: ToolContext, side: str = "black") -> Dict[str, Any]:
    """Choose one legal move for the given side from the current board state."""
    return choose_ai_move(side=side)


CHESS_AI_INSTRUCTION = """
You are a chess move planner.
Always call get_ai_move exactly once.
Respond only with the returned verified_fact and do not invent any move.
"""


root_chess_ai_agent = Agent(
    name="chess_ai_agent",
    model=MODEL,
    description="Returns one legal chess move for a side.",
    instruction=CHESS_AI_INSTRUCTION,
    tools=[get_ai_move],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
    ),
)

