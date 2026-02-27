# Multi-Agent System with Google ADK

This directory contains examples and runnable agents built with [Google's Agent Development Kit (ADK)](https://github.com/GoogleCloudPlatform/devrel-demos), using LiteLLM for model inference (e.g. local or custom endpoints).

In addition to local ADK usage, this folder also backs the **Talk agents HTTP service** used when Talk runs in *agent mode* (travel planner).

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

Run any of the above from this directory after setup. The **Fix my city** agent stores complaints in SQLite (see `fix-my-city/storage.py`); run `python3 test_storage.py` from `fix-my-city/` to run storage tests.

## Use with the Talk stack

When you run Talk via Docker, an **agents** container is built from [`agents/Dockerfile`](Dockerfile) and exposes:

- `POST /v1/agents/{agent_name}/chat` – `agent_name` may be `travel_planner`, `viva_examiner`, or `fix_my_city`.

The service:

- Imports the travel-planner `root_agent` from `travel-planner-sub-agents/agent.py`.
- Imports the viva examiner `root_viva_agent` from `viva-examiner/agent.py`.
- Imports the fix-my-city agent `root_fix_my_city_agent` from `fix-my-city/agent.py` (complaints stored in SQLite; see `fix-my-city/storage.py`).
- Uses LiteLlm (`google.adk.models.lite_llm.LiteLlm`) configured via environment:

  ```env
  LITELLM_MODEL_NAME="openai/gemma3"
  LITELLM_API_BASE="http://vllm-server:10802/v1"  # in integrated stack
  LITELLM_API_KEY="sk-..."                        # or your real key
  ```

- Receives `{ "session_id": "...", "message": "..." }` from the Talk backend and returns `{ "reply": "..." }`.

The Talk backend (`talk-server/main.py`) routes requests here when the UI selects **Travel planner agent** mode, while still using the same ASR/TTS pipeline.

## Web UI

To use the ADK web interface for running and inspecting agents:

```bash
adk web
```

## References

- **Codelab:** [Production-ready AI with Google Cloud – Build a multi-agent system with ADK](https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/3-developing-agents/build-a-multi-agent-system-with-adk#0)
- **Source repo (Google DevRel demos):**

  ```bash
  git clone --depth 1 https://github.com/GoogleCloudPlatform/devrel-demos.git devrel-demos-multiagent-lab
  ```
