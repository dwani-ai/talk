# Multi-Agent System with Google ADK

This directory contains examples and runnable agents built with [Google's Agent Development Kit (ADK)](https://github.com/GoogleCloudPlatform/devrel-demos), using LiteLLM for model inference (e.g. local or custom endpoints).

In addition to local ADK usage, this folder also backs the **Talk agents HTTP service** used when Talk runs in *agent mode*.

## Prerequisites

- **Python 3.10**
- An AI inference endpoint (local or remote) compatible with LiteLLM

## Setup

1. **Create and activate a virtual environment:**

   ```bash
   python3.10 -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment** — create a `.env` file in this directory (or in each agent subdirectory as needed) with your model settings:

   ```env
   LITELLM_MODEL_NAME="openai/gemma3"
   LITELLM_API_BASE="https://qwen-api"
   LITELLM_API_KEY="sk-dummy"
   ```

   Adjust `LITELLM_MODEL_NAME`, `LITELLM_API_BASE`, and `LITELLM_API_KEY` for your inference server.

## Verify AI inference

From this directory (with `venv` activated):

```bash
adk run test_api
```

This runs the `test_api` agent and confirms that the ADK can reach your model via LiteLLM.

## Example agents

Each example corresponds to a section in the [Google codelab: Build a multi-agent system with ADK](https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/3-developing-agents/build-a-multi-agent-system-with-adk#0).

| Example | Command | Codelab section |
|--------|--------|------------------|
| **Travel planner (sub-agents)** | `adk run travel-planner-sub-agents` | [§6 – Sub-agents](https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/3-developing-agents/build-a-multi-agent-system-with-adk#6) |
| **Viva/voce examiner** | `adk run viva-examiner` | Custom viva/oral-exam practice agent |
| **Fix my city** | — | City complaint registration and status; used via Talk UI |
| **Orchestrator** | — | Routes each turn to travel planner, viva, or fix-my-city based on user intent; used via Talk UI |
| **Warehouse orchestrator** | — | Routes warehouse robot commands and returns live `warehouse_state` |
| **Chess orchestrator** | — | Routes chess commands and returns live `chess_state` |

Run any of the above from this directory after setup. The **Fix my city** agent stores complaints in SQLite (see `fix-my-city/storage.py`); run `python3 test_storage.py` from `fix-my-city/` to run storage tests. The **Orchestrator** agent reuses the same LiteLlm configuration and delegates each request to the appropriate specialist agent.

## Use with the Talk stack

When you run Talk via Docker, an **agents** container is built from [`agents/Dockerfile`](Dockerfile) and exposes:

- `POST /v1/agents/{agent_name}/chat` – `agent_name` may be `travel_planner`, `viva_examiner`, `fix_my_city`, or `orchestrator`.
- `GET /v1/warehouse/state` – warehouse state snapshot for the Warehouse tab.
- `GET /v1/chess/state` – chess state snapshot for the Chess tab.
- `POST /v1/agents/{agent_name}/chat` – `agent_name` may be `travel_planner`, `viva_examiner`, `fix_my_city`, `orchestrator`, `warehouse_orchestrator`, or `chess_orchestrator`.

The service:

- Imports the travel-planner `root_agent` from `travel-planner-sub-agents/agent.py`.
- Imports the viva examiner `root_viva_agent` from `viva-examiner/agent.py`.
- Imports the fix-my-city agent `root_fix_my_city_agent` from `fix-my-city/agent.py` (complaints stored in SQLite; see `fix-my-city/storage.py`).
- Imports the orchestrator agent `root_orchestrator_agent` from `orchestrator/agent.py`, which internally delegates each turn to travel_planner, viva_examiner, or fix_my_city via ADK runners.
- Imports the warehouse orchestrator agent `root_warehouse_orchestrator_agent` from `warehouse/orchestrator_agent.py`.
- Imports the chess orchestrator agent `root_chess_orchestrator_agent` from `chess/orchestrator_agent.py`.
- Uses LiteLlm (`google.adk.models.lite_llm.LiteLlm`) configured via environment:

  ```env
  LITELLM_MODEL_NAME="openai/gemma3"
  LITELLM_API_BASE="http://vllm-server:10802/v1"  # in integrated stack
  LITELLM_API_KEY="sk-..."                        # or your real key
  ```

- Receives `{ "session_id": "...", "message": "..." }` from the Talk backend and returns `{ "reply": "..." }`.

The Talk backend (`talk-server/main.py`) routes requests here when the UI selects any agent mode, while still using the same ASR/TTS pipeline.

## Architecture

At a high level the agents service looks like this:

- **FastAPI HTTP layer** (`service_main.py`)
  - Defines the `/v1/agents/{agent_name}/chat` endpoint and request/response models.
  - Handles CORS and basic error mapping to HTTP 4xx/5xx.

- **Session and runners**
  - Uses a single `InMemorySessionService` shared across all agents.
  - For each registered agent (`travel_planner`, `viva_examiner`, `fix_my_city`, `orchestrator`) creates a `Runner` with:
    - The corresponding ADK `Agent` (`root_agent`, `root_viva_agent`, `root_fix_my_city_agent`, `root_orchestrator_agent`).
    - A common `app_name` (from `AGENTS_APP_NAME`).
    - The shared session service.
  - On each HTTP call:
    - Ensures an ADK session exists for `(user_id=session_id, session_id=session_id)`.
    - Streams events from `Runner.run(...)` and concatenates the final text parts into the `reply` field.

- **Agents and tools**
  - Travel planner:
    - Root agent orchestrates two sub‑agents (`travel_brainstormer`, `attractions_planner`) and uses tools like `save_attractions_to_state` to build state.
  - Viva examiner:
    - Single agent that uses a tool to record question/answer/score/feedback into its session state.
  - Fix my city:
    - Single agent with tools that read/write complaints from a SQLite database.
  - Orchestrator:
    - Single agent with tools that internally call the three domain agents via ADK runners and return their replies.

In production, the agents service is typically fronted by Docker networking:

```mermaid
flowchart LR
  backend[Talk server] -->|HTTP /v1/agents/.../chat| agentsSvc[Agents service (FastAPI + ADK)]
  agentsSvc -->|LiteLlm| llm[LLM endpoint (vLLM/OpenAI)]
  agentsSvc -->|SQLite| db[(Fix-my-city DB)]
```

## Tech stack

- **Core**
  - Python 3.10+
  - FastAPI + Uvicorn for the HTTP service (`service_main.py`)
  - Google ADK (`google-adk`) for agent definitions, tools, and runners
  - LiteLlm adapter for calling the model endpoint

- **Persistence**
  - In‑memory session state via `InMemorySessionService` (per app name + user + session)
  - SQLite database for fix‑my‑city complaints (see `fix-my-city/storage.py`), with Docker volumes used for durability in integrated stacks

- **Model & infra integration**
  - LITELLM_MODEL_NAME / LITELLM_API_BASE / LITELLM_API_KEY configure the inference endpoint (vLLM, Qwen, or other OpenAI‑compatible servers)
  - Docker image built from `agents/Dockerfile`, wired into `compose.yml`, `compose-dev.yml`, and the integrated stacks

## Web UI

To use the ADK web interface for running and inspecting agents directly (outside of Talk):

```bash
adk web
```

## References

- **Codelab:** [Production-ready AI with Google Cloud – Build a multi-agent system with ADK](https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/3-developing-agents/build-a-multi-agent-system-with-adk#0)
- **Source repo (Google DevRel demos):**

  ```bash
  git clone --depth 1 https://github.com/GoogleCloudPlatform/devrel-demos.git devrel-demos-multiagent-lab
  ```
