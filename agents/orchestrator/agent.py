import asyncio
import logging
import os
from importlib import util as importlib_util
from typing import Any, Dict

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

import pathlib


load_dotenv()


logger = logging.getLogger("orchestrator_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)

_SKILLS_ROOT = pathlib.Path(__file__).resolve().parents[1] / "skills"
_COMMON_SKILL = load_skill_from_dir(_SKILLS_ROOT / "common" / "tts-language")
_ROUTING_SKILL = load_skill_from_dir(_SKILLS_ROOT / "orchestrator" / "routing")
_SKILL_TOOLSET = skill_toolset.SkillToolset(skills=[_COMMON_SKILL, _ROUTING_SKILL])

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)


def _load_agent(path: str, module_name: str, attr_name: str):
    spec = importlib_util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load spec for {module_name} at {path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    try:
        return getattr(module, attr_name)
    except AttributeError as exc:  # pragma: no cover
        raise RuntimeError(f"{attr_name} not found in module {module_name}") from exc


TRAVEL_AGENT_PATH = os.path.join(ROOT_DIR, "travel-planner-sub-agents", "agent.py")
VIVA_AGENT_PATH = os.path.join(ROOT_DIR, "viva-examiner", "agent.py")
FIX_MY_CITY_AGENT_PATH = os.path.join(ROOT_DIR, "fix-my-city", "agent.py")

travel_root_agent = _load_agent(TRAVEL_AGENT_PATH, "travel_planner_agent", "root_agent")
viva_root_agent = _load_agent(VIVA_AGENT_PATH, "viva_examiner_agent", "root_viva_agent")
fix_my_city_root_agent = _load_agent(
    FIX_MY_CITY_AGENT_PATH, "fix_my_city_agent", "root_fix_my_city_agent"
)


APP_NAME = os.getenv("AGENTS_APP_NAME", "talk_orchestrator")
_session_service = InMemorySessionService()
_known_sessions: set[str] = set()


travel_runner = Runner(
    agent=travel_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)
viva_runner = Runner(
    agent=viva_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)
fix_my_city_runner = Runner(
    agent=fix_my_city_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)


def _session_id_from_context(tool_context: ToolContext) -> str:
    return (
        getattr(tool_context, "session_id", None)
        or getattr(getattr(tool_context, "session", None), "id", None)
        or "default"
    )


async def _ensure_session_async(user_id: str, session_id: str) -> None:
    """Create an ADK session if it does not already exist for this app."""
    key = f"{user_id}:{session_id}"
    if key in _known_sessions:
        return
    await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    _known_sessions.add(key)


async def _run_subagent_message_async(runner: Runner, session_id: str, message: str) -> str:
    await _ensure_session_async(user_id=session_id, session_id=session_id)

    content = types.Content(role="user", parts=[types.Part(text=message)])
    events = runner.run_async(
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
        raise RuntimeError("Sub-agent returned empty response")

    return " ".join(" ".join(final_text_parts).split())


async def call_travel_planner(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the travel planner agent."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(travel_runner, session_id, message)
    tool_context.state["active_agent"] = "travel_planner"
    return {"reply": reply, "target": "travel_planner"}


async def call_viva_examiner(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the viva / oral exam agent."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(viva_runner, session_id, message)
    tool_context.state["active_agent"] = "viva_examiner"
    return {"reply": reply, "target": "viva_examiner"}


async def call_fix_my_city(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the fix-my-city complaints agent."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(fix_my_city_runner, session_id, message)
    tool_context.state["active_agent"] = "fix_my_city"
    return {"reply": reply, "target": "fix_my_city"}


root_orchestrator_agent = Agent(
    name="orchestrator",
    model=MODEL,
    description="Routes user queries to travel, viva, or fix-my-city agents.",
    instruction=(
        "You are a router agent. Use your skills to load the detailed routing policy, then "
        "delegate with exactly one of the available routing tools."
    ),
    tools=[_SKILL_TOOLSET, call_travel_planner, call_viva_examiner, call_fix_my_city],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.3,
    ),
)

