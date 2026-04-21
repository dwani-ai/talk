import os
import sys
import logging
from typing import List, Dict

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types

import pathlib


load_dotenv()


logger = logging.getLogger("viva_examiner_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)

_SKILLS_ROOT = pathlib.Path(__file__).resolve().parents[1] / "skills"
_COMMON_SKILL = load_skill_from_dir(_SKILLS_ROOT / "common" / "tts-language")
_VIVA_SKILL = load_skill_from_dir(_SKILLS_ROOT / "viva-examiner" / "viva-exam-flow")
_SKILL_TOOLSET = skill_toolset.SkillToolset(skills=[_COMMON_SKILL, _VIVA_SKILL])


def record_answer_result(
    tool_context: ToolContext,
    question: str,
    answer: str,
    score: int,
    feedback: str,
) -> Dict[str, str]:
    """Record a student's answer, score, and feedback into the session state.

    The agent should call this tool after evaluating each answer.
    """
    state = tool_context.state

    answers: List[Dict] = state.get("answers", [])
    answers.append(
        {
            "question": question,
            "answer": answer,
            "score": score,
            "feedback": feedback,
        }
    )
    state["answers"] = answers

    total_score = state.get("total_score", 0)
    num_answered = state.get("num_answered", 0)
    try:
        total_score += int(score)
    except Exception:
        # If score isn't an int, still store it in the answer but don't break.
        pass
    else:
        num_answered += 1

    state["total_score"] = total_score
    state["num_answered"] = num_answered

    return {"status": "recorded"}


root_viva_agent = Agent(
    name="viva_examiner",
    model=MODEL,
    description="Conducts viva/voce style oral exams with scoring and feedback.",
    instruction=(
        "You are a viva/voce examiner. Use your skills to load the detailed exam flow "
        "(questions, scoring, feedback, language mirroring, and brevity) and follow them."
    ),
    tools=[_SKILL_TOOLSET, record_answer_result],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.3,
    ),
)

