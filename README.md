# Talk — dwani.ai

**Conversational AI for Indian languages.**  
Try it: [talk.dwani.ai](https://talk.dwani.ai)

Built to make AI accessible to everyone, using open-weight models (e.g. Nvidia L4 on Google Cloud).  
We’d love your feedback and to hear how you’d use it.

---

## Prerequisites

- **Local run:** Python 3.10+, and ASR / TTS / LLM services running (see [External services](#external-services)).
- **Docker:** Docker and Docker Compose. For [Integrated stack](#production-integrated-stack): GPU with ≥24 GB VRAM.

---

## Quick start

| Goal | Command |
|------|--------|
| **Local (Python)** | Set env URLs → `python main.py` (see [Run locally](#run-locally-python)). |
| **Docker (host ASR/TTS/LLM)** | `cp .env.example .env` → `docker compose up -d` → open http://localhost |
| **Docker dev (build from source)** | `docker compose -f compose-dev.yml up -d --build` |
| **Production (integrated TTS + LLM)** | ASR on host → `docker compose -f compose-integrated.yml up -d` |

---

## Run locally (Python)

Use when ASR, TTS, and LLM run on the **same machine** (e.g. `0.0.0.0:10803`, `10804`, `10802`):

```bash
export DWANI_API_BASE_URL_TTS="http://0.0.0.0:10804"
export DWANI_API_BASE_URL_ASR="http://0.0.0.0:10803"
export DWANI_API_BASE_URL_LLM="http://0.0.0.0:10802"
python3.10 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

API: http://localhost:8000 (no UI; use curl or the UI from another setup).

---

## Run with Docker (UI + backend)

Use when **Talk** runs in Docker but **ASR / TTS / LLM** run on the **host**. The containers must use `host.docker.internal` to reach the host (do **not** use `0.0.0.0` in `.env`).

```bash
cp .env.example .env
# Edit .env if your ASR/TTS/LLM ports differ (defaults: 10803, 10804, 10802)
docker compose up -d
```

Open **http://localhost** for the UI.

### Development (build from source)

```bash
docker compose -f compose-dev.yml up -d --build
```

---

## Production (integrated stack)

Runs **Talk + UI + TTS (tts-indic-server) + LLM (vLLM)** in one stack. **ASR** must still run on the host (or set `DWANI_API_BASE_URL_ASR` in `.env`).

**Requirements:** GPU with ≥24 GB VRAM.

```bash
# Ensure ASR is reachable (e.g. on host at 10803)
docker compose -f compose-integrated.yml up -d
```

Open **http://localhost**. TTS and LLM are wired to the containers; only ASR uses the host by default.

---

## Agent mode (travel planner & viva examiner)

The Talk UI can route user turns either:

- **Directly to the LLM** (default), or  
- **Through an ADK-powered agent** built with Google ADK and LiteLlm.

Currently there are four agents:

- **Travel planner agent** – multi-agent travel-planning assistant.
- **Viva/voce examiner** – single-agent viva/oral-exam examiner that scores each answer and gives feedback.
- **Fix my city agent** – register city complaints (city, area, date, time, type, description) and check status of previous complaints; complaints are stored durably in SQLite.
- **Orchestrator agent** – a smart router that looks at each user turn and delegates it to the travel planner, viva examiner, or fix-my-city agent as appropriate.
- **Warehouse orchestrator** – controls UAV/UGV/Arm robots and returns verified `warehouse_state` for the 3D view.
- **Chess orchestrator** – runs chess commands with deterministic rules and returns verified `chess_state` for the board.

When you pick **“Travel planner agent”** in the UI:

- The backend still does **ASR → text**.
- Instead of calling the LLM directly, it calls the **agents service** (`/v1/agents/travel_planner/chat`).
- The agents service runs the ADK `root_agent` from `agents/travel-planner-sub-agents/agent.py`, which in turn coordinates sub‑agents to:
  - Help pick a country.
  - Plan attractions and store them in state.
- The final agent reply is sent to **TTS → audio** and played back just like normal LLM mode.

When you pick **“Viva/voce examiner”** in the UI:

- The backend still does **ASR → text** (or accepts typed text).
- Instead of calling the LLM directly, it calls the **agents service** (`/v1/agents/viva_examiner/chat`).
- The ADK `root_viva_agent` in `agents/viva-examiner/agent.py` conducts an oral exam for the chosen subject:
  - Asks short, clear viva questions.
  - Scores each answer (0–10) and provides brief feedback.
  - Summarizes performance (average score + strengths/weaknesses) at the end of the session.
- The final agent reply is sent to **TTS → audio** and played back just like normal LLM mode.

When you pick **“Orchestrator agent”** in the UI:

- The backend calls the agents service (`/v1/agents/orchestrator/chat`).
- The ADK `root_orchestrator_agent` in `agents/orchestrator/agent.py` inspects each message and forwards it to the appropriate specialist agent (`travel_planner`, `viva_examiner`, or `fix_my_city`).
- The specialist agent’s reply is then sent to **TTS → audio** and played back just like normal LLM mode.

How it runs:

- **Docker (host ASR/TTS/LLM)**: `compose.yml` and `compose-dev.yml` include an `agents` service built from `agents/Dockerfile`.  
- **Production integrated stack**: `compose-integrated.yml` adds an `agents` service wired to the internal `vllm-server` and exposes it to the backend via `DWANI_AGENT_BASE_URL`.

For more details about the ADK setup and local agent experiments, see [`agents/README.md`](agents/README.md).

---

## Chess tab (agent-driven)

Talk includes a dedicated **Chess** tab using the same end-to-end pattern as Warehouse:

- UI sends chat commands to `/v1/chat` with `agent_name: "chess_orchestrator"`.
- Agents service executes deterministic chess commands and returns `chess_state`.
- UI applies `chess_state` immediately and also polls `/v1/chess/state` as a fallback.

### Supported v1 commands

- `new game`
- `new game human vs ai as white`
- `new game human vs human`
- `e2 to e4` (also `e2e4`)
- `ai move`
- `show board state`

Core movement/capture/turn-order rules are enforced deterministically. Advanced rules (check/checkmate/stalemate/castling/en-passant) are deferred.

---

## Architecture overview

At a high level Talk consists of:

- **Frontend (Talk UI)** – React/Vite single-page app in `talk-ui/`:
  - Runs in the browser, records audio, and shows a simple conversation sidebar.
  - Calls the backend `/v1/speech_to_speech` (voice) or `/v1/chat` (text) APIs with a `X-Session-ID` header to preserve context.
  - Lets the user choose between direct LLM mode and several agent modes (travel, viva, fix‑my‑city, all‑in‑one assistant).

- **Backend API (Talk server)** – FastAPI app in `talk-server/`:
  - Exposes `/v1/speech_to_speech`:
    - Accepts audio → sends to **ASR** → gets text.
    - Sends text either to **LLM** directly or to the **agents** HTTP service (when in agent mode).
    - Sends the reply text to **TTS** and streams back MP3.
  - Exposes `/v1/chat` for typed text only:
    - Maintains short in‑memory session history per `X-Session-ID`.
    - Sends text to LLM or to the agents service.
  - Uses in‑memory session storage only (no user data persisted on disk).

- **Agents service** – FastAPI + Google ADK app in `agents/`:
  - Exposes `POST /v1/agents/{agent_name}/chat` to the backend:
    - `travel_planner`, `viva_examiner`, `fix_my_city`, `orchestrator`.
  - Each agent is a Google ADK `Agent` wired through a `Runner` with an `InMemorySessionService`.
  - Agents themselves call out to the same LLM endpoint via LiteLlm, and in the case of **Fix my city**, also store complaints in SQLite.

- **External model services**:
  - **ASR** (speech → text) – `asr-indic-server` (default port `10803`).
  - **TTS** (text → speech) – `tts-indic-server` (default port `10804`).
  - **LLM** – vLLM / OpenAI‑compatible HTTP API (default port `10802`), backed by Gemma or Qwen in the provided compose files.

End‑to‑end architecture (including agents):

```mermaid
flowchart LR
  subgraph client["Client"]
    talkUi["TalkUI"]
  end

  subgraph api["TalkServer_FastAPI"]
    chatEp["ChatEndpoint_/v1/chat"]
    s2sEp["Speech2Speech_/v1/speech_to_speech"]
  end

  subgraph modelServices["ModelAndSpeechServices"]
    asrSvc["ASRServer"]
    ttsSvc["TTSServer"]
    llmSvc["LLMServer_vLLM_or_Qwen"]
  end

  subgraph agentsService["AgentsService_FastAPI_ADK"]
    httpChat["AgentsHTTP_/v1/agents/{agent_name}/chat"]

    subgraph adkCore["ADKRunnersAndSessions"]
      sessionStore["InMemorySessionService"]
      runnerTravel["Runner_travel_planner"]
      runnerViva["Runner_viva_examiner"]
      runnerCity["Runner_fix_my_city"]
      runnerOrch["Runner_orchestrator"]
    end

    subgraph adkAgents["ADKAgents"]
      agentTravel["TravelPlannerAgent"]
      agentViva["VivaExaminerAgent"]
      agentCity["FixMyCityAgent"]
      agentOrch["OrchestratorAgent"]
    end

    subgraph cityStorage["FixMyCityStorage"]
      cityDb["SQLiteComplaintsDB"]
    end
  end

  %% UI → Backend
  talkUi -->|text_or_audio\nX-Session-ID| chatEp
  talkUi -->|audio\nX-Session-ID| s2sEp

  %% Speech path
  s2sEp -->|audio| asrSvc
  asrSvc -->|text| s2sEp

  %% Backend → LLM or agents
  chatEp -->|mode=llm\ntext_plus_context| llmSvc
  chatEp -->|mode=agent\ntext_plus_session_id| httpChat
  s2sEp -->|text_plus_mode\n(agent_or_llm)| chatEp

  %% HTTP → runners
  httpChat -->|agent_name=travel_planner| runnerTravel
  httpChat -->|agent_name=viva_examiner| runnerViva
  httpChat -->|agent_name=fix_my_city| runnerCity
  httpChat -->|agent_name=orchestrator| runnerOrch

  %% Runners ↔ agents
  runnerTravel --> agentTravel
  runnerViva --> agentViva
  runnerCity --> agentCity
  runnerOrch --> agentOrch

  %% Orchestrator delegations
  agentOrch -->|tool_call_travel_planner| runnerTravel
  agentOrch -->|tool_call_viva_examiner| runnerViva
  agentOrch -->|tool_call_fix_my_city| runnerCity

  %% Agents → LLM
  agentTravel -->|LiteLlm_calls| llmSvc
  agentViva -->|LiteLlm_calls| llmSvc
  agentCity -->|LiteLlm_calls| llmSvc
  agentOrch -->|LiteLlm_calls| llmSvc

  %% Fix-my-city DB
  agentCity -->|create_get_update_complaints| cityDb

  %% Backend → TTS → UI
  chatEp -->|reply_text| ttsSvc
  s2sEp -->|reply_text| ttsSvc
  ttsSvc -->|mp3_audio| talkUi
```

---

## Tech stack

- **Frontend (Talk UI)**
  - React + Vite SPA in `talk-ui/`.
  - Minimal CSS, no framework dependency for styling.
  - Uses browser MediaRecorder for mic capture and fetch for API calls.

- **Backend (Talk server)**
  - Python 3.10+, FastAPI, Uvicorn.
  - `httpx` for outbound HTTP to ASR/TTS/LLM/agents.
  - OpenAI Python client for OpenAI‑compatible chat completions.
  - `slowapi` for rate limiting, Pydantic v2 for request/response models.

- **Agents service**
  - Python 3.10+, FastAPI, Uvicorn in `agents/`.
  - Google ADK (`google-adk`) for defining agents, tools, and runners.
  - LiteLlm (`google.adk.models.lite_llm.LiteLlm`) as the model adapter, pointed at the same OpenAI‑compatible LLM endpoint.
  - In‑memory session state via `InMemorySessionService`.
  - SQLite (via `sqlite3`) for persistent complaint storage in the **Fix my city** workflow.

- **Model & speech stack**
  - ASR: [`asr-indic-server`](https://github.com/dwani-ai/asr-indic-server) (gRPC/HTTP service).
  - TTS: [`tts-indic-server`](https://github.com/dwani-ai/tts-indic-server).
  - LLM: vLLM (`vllm/vllm-openai` image) serving models such as Gemma‑3 or Qwen with an OpenAI‑compatible API.

- **Infrastructure**
  - Docker + Docker Compose for local dev and production‑style integrated stacks.
  - Optional **GPU** (NVIDIA) for integrated vLLM + TTS + ASR stacks.
  - Environment‑driven configuration (`.env`, Docker `environment:`) for all service URLs and model names.

---

## Build Docker images

Build and tag images for use with `compose.yml` or `compose-integrated.yml`:

**Backend (talk-server):**
```bash
cd talk-server
docker build -t dwani/talk-server:latest -f Dockerfile .
```

**Frontend (talk-ux):**
```bash
cd talk-ui
docker build -t dwani/talk-ux:latest -f Dockerfile .
```

**Agents (agents):**
```bash
cd agents
docker build -t dwani/talk-agents:latest -f Dockerfile .
```


---

## External services

| Service | Default port | Repo / notes |
|--------|--------------|--------------|
| **ASR** | 10803 | [asr-indic-server](https://github.com/dwani-ai/asr-indic-server) |
| **TTS** | 10804 | [tts-indic-server](https://github.com/dwani-ai/tts-indic-server) |
| **LLM** | 10802 | vLLM / OpenAI-compatible; see [docs/llm-setup.md](docs/llm-setup.md) |

---

## Test (curl)

```bash
curl -X POST 'http://localhost:8000/v1/speech_to_speech?language=kannada' \
  -H 'Content-Type: multipart/form-data' -F 'file=@kannada_sample.wav' -o test.mp3
```

If the UI runs on port 80 and proxies `/v1` to the backend, use `http://localhost/v1/speech_to_speech?...` instead.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DWANI_API_BASE_URL_ASR` | Yes | ASR service URL (e.g. `http://host.docker.internal:10803` in Docker). |
| `DWANI_API_BASE_URL_TTS` | Yes | TTS service URL. |
| `DWANI_API_BASE_URL_LLM` | Yes | LLM service URL (OpenAI-compatible). |
| `DWANI_LLM_MODEL` | No | Model name (default: `gemma3`). |
| `DWANI_AGENT_BASE_URL` | No | Base URL for the agents HTTP service used in **agent mode** (e.g. `http://agents:8081` in Docker). |

See [.env.example](.env.example) for optional timeouts, upload limits, and session context.
