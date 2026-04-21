import os
import random
from typing import Any, Dict

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from chess.state_store import get_state
from chess.commands import list_legal_moves_for_side

import pathlib

load_dotenv()

MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)

_SKILLS_ROOT = pathlib.Path(__file__).resolve().parents[1] / "skills"
_COMMON_SKILL = load_skill_from_dir(_SKILLS_ROOT / "common" / "tts-language")
_AI_SKILL = load_skill_from_dir(_SKILLS_ROOT / "chess" / "chess-ai-planner")
_SKILL_TOOLSET = skill_toolset.SkillToolset(skills=[_COMMON_SKILL, _AI_SKILL])

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


root_chess_ai_agent = Agent(
    name="chess_ai_agent",
    model=MODEL,
    description="Returns one legal chess move for a side.",
    instruction="You are a chess move planner. Use your skills and follow them strictly.",
    tools=[_SKILL_TOOLSET, get_ai_move],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
    ),
)

