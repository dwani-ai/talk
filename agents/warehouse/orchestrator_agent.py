import asyncio
import logging
import os
import sys
from importlib import util as importlib_util
from typing import Any, Dict, List

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

_WAREHOUSE_DIR = os.path.dirname(os.path.abspath(__file__))
if _WAREHOUSE_DIR not in sys.path:
  sys.path.insert(0, _WAREHOUSE_DIR)

from state_store import get_state  # type: ignore[import-not-found]


load_dotenv()


logger = logging.getLogger("warehouse_orchestrator_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


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


UAV_AGENT_PATH = os.path.join(CURRENT_DIR, "uav_agent.py")
UGV_AGENT_PATH = os.path.join(CURRENT_DIR, "ugv_agent.py")
ARM_AGENT_PATH = os.path.join(CURRENT_DIR, "arm_agent.py")

uav_root_agent = _load_agent(UAV_AGENT_PATH, "warehouse_uav_agent", "root_uav_agent")
ugv_root_agent = _load_agent(UGV_AGENT_PATH, "warehouse_ugv_agent", "root_ugv_agent")
arm_root_agent = _load_agent(ARM_AGENT_PATH, "warehouse_arm_agent", "root_arm_agent")


APP_NAME = os.getenv("AGENTS_APP_NAME", "talk_warehouse")
_session_service = InMemorySessionService()
_known_sessions: set[str] = set()


uav_runner = Runner(
    agent=uav_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)
ugv_runner = Runner(
    agent=ugv_root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)
arm_runner = Runner(
    agent=arm_root_agent,
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


async def call_uav(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the UAV mapping agent."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(uav_runner, session_id, message)
    tool_context.state["active_robot"] = "uav"
    return {"reply": reply, "target": "uav"}


async def call_ugv(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the UGV ground-mover agent."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(ugv_runner, session_id, message)
    tool_context.state["active_robot"] = "ugv"
    return {"reply": reply, "target": "ugv"}


async def call_arm(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """Delegate this turn to the arm / stacking agent."""
    session_id = _session_id_from_context(tool_context)
    reply = await _run_subagent_message_async(arm_runner, session_id, message)
    tool_context.state["active_robot"] = "arm"
    return {"reply": reply, "target": "arm"}


def get_robots_state(tool_context: ToolContext) -> Dict[str, Any]:
    """Return a snapshot of all robots with their positions, status, and current tasks."""
    state = get_state()
    robots: List[Dict[str, Any]] = state.get("robots", [])
    summary = [
        {
            "id": r.get("id"),
            "type": r.get("type"),
            "status": r.get("status"),
            "current_task": r.get("current_task"),
            "position": r.get("position"),
        }
        for r in robots
    ]
    return {
        "robots": summary,
        "warehouse": state.get("warehouse", {}),
    }


WAREHOUSE_ORCHESTRATOR_INSTRUCTION = """
You are a warehouse robotics orchestrator. You manage three specialist robots:

- UAV: maps items by flying and scanning areas.
- UGV: moves items on the ground.
- Arm: stacks and places items on shelves.

Users may give high-level commands like:
- "Scan the north aisle and show me the items there."
- "Move box A-1 next to the loading dock."
- "Stack the three parcels on rack 2."

They may also ask for a status update, like:
- "What are the robots doing right now?"
- "Where are all the robots and what are their tasks?"

Behavior:
- Detect the user's intent and choose exactly one tool:
  - call_uav for mapping / scanning / aerial movements.
  - call_ugv for moving items on the floor.
  - call_arm for stacking / unstacking / placing on shelves.
  - get_robots_state when the user asks about current robot state or tasks.
- If you are unsure which robot should handle a request, ask ONE short clarification question.
- You MUST call at least one tool for every user request; never answer based only on your own reasoning.
- For movement requests, ensure the relevant sub-agent actually calls its movement tools
  and base your summary on the positions returned by those tools.
- For status questions ("what are the robots doing?"), ALWAYS call get_robots_state and answer
  only using the positions, status, and current_task values returned by that tool.

Language and style:
- Detect the user's language and respond in the SAME language.
- Keep responses concise and TTS-friendly (1–3 short sentences).
"""


root_warehouse_orchestrator_agent = Agent(
    name="warehouse_orchestrator",
    model=MODEL,
    description="Routes warehouse tasks to UAV, UGV, or arm robot agents and can report current robot state.",
    instruction=WAREHOUSE_ORCHESTRATOR_INSTRUCTION,
    tools=[call_uav, call_ugv, call_arm, get_robots_state],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.25,
    ),
)

