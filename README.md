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
