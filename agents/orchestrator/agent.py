import logging
import os
from importlib import util as importlib_util
from typing import Any, Dict

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types


load_dotenv()


logger = logging.getLogger("orchestrator_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


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


def _run_subagent_message(runner: Runner, session_id: str, message: str) -> str:
    content = types.Content(role="user", parts=[types.Part(text=message)])
    events = runner.run(user_id=session_id, session_id=session_id, new_message=content)

    final_text_parts: list[str] = []
    for event in events:
        if getattr(event, "is_final_response", None) and event.is_final_response() and event.content:
            for p in event.content.parts:
                text = getattr(p, "text", None)
                if text:
                    final_text_parts.append(str(text))

    if not final_text_parts:
        raise RuntimeError("Sub-agent returned empty response")

    return " ".join(" ".join(final_text_parts).split())


def call_travel_planner(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the travel planner agent."""
    session_id = _session_id_from_context(tool_context)
    reply = _run_subagent_message(travel_runner, session_id, message)
    tool_context.state["active_agent"] = "travel_planner"
    return {"reply": reply, "target": "travel_planner"}


def call_viva_examiner(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the viva / oral exam agent."""
    session_id = _session_id_from_context(tool_context)
    reply = _run_subagent_message(viva_runner, session_id, message)
    tool_context.state["active_agent"] = "viva_examiner"
    return {"reply": reply, "target": "viva_examiner"}


def call_fix_my_city(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the fix-my-city complaints agent."""
    session_id = _session_id_from_context(tool_context)
    reply = _run_subagent_message(fix_my_city_runner, session_id, message)
    tool_context.state["active_agent"] = "fix_my_city"
    return {"reply": reply, "target": "fix_my_city"}


ORCHESTRATOR_INSTRUCTION = """
You are an orchestrator agent that routes each user message to one of three specialist agents:

- Travel planner: plans trips and attractions.
- Viva / oral examiner: conducts viva exams with scoring and feedback.
- Fix my city: registers city complaints and checks complaint status.

Users may speak or type in Kannada, Hindi, Tamil, Malayalam, Telugu, Marathi, English, or German.
Detect the user's language and always respond in the SAME language.

Behavior:
- Read the user's latest message and decide whether it is about:
  1) Travel planning,
  2) Viva / exam practice, or
  3) City complaints (registering a complaint or checking a complaint status).
- If the intent is unclear, ask ONE short clarification question before choosing.
- Once you know the intent, call exactly ONE tool:
  - call_travel_planner
  - call_viva_examiner
  - call_fix_my_city
- Use the 'message' argument to pass the user's message (or a brief reformulation) to the chosen agent.
- After the tool returns, use its 'reply' field as your main response text.

State:
- You may use the 'active_agent' field in state to remember which agent is currently handling the conversation.
- If the user's new message clearly continues the same topic as before, keep using the same agent.
- If the user clearly changes topic (for example, from travel to a city complaint), switch to the appropriate agent.

Do NOT answer domain questions by yourself. Always delegate to the appropriate specialist agent using the tools.
Keep your own wording very short and let the specialist agent do the main talking.
"""


root_orchestrator_agent = Agent(
    name="orchestrator",
    model=MODEL,
    description="Routes user queries to travel, viva, or fix-my-city agents.",
    instruction=ORCHESTRATOR_INSTRUCTION,
    tools=[call_travel_planner, call_viva_examiner, call_fix_my_city],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.3,
    ),
)

