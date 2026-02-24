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

## Build Docker images

Build and tag images for use with `compose.yml` or `compose-integrated.yml`:

**Backend (talk-server):**
```bash
cd talk-server
docker build -t dwani/talk-server:latest -f Dockerfile .
```

**Frontend (talk-ux):**
```bash
cd talk-ux
docker build -t dwani/talk-ux:latest -f Dockerfile .
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

## Public API endpoints

These endpoints are available for external API consumers (in addition to the Talk UI).

### 1. Transcribe (ASR)

- **POST** `/v1/audio/transcriptions`
- **Body**: `multipart/form-data` with `file` and `language` query param.

```bash
curl -X POST 'http://localhost:8000/v1/audio/transcriptions?language=kannada' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@kannada_sample.wav' |
  jq
```

Response:

```json
{ "text": "transcribed text" }
```

### 2. Text‑to‑Speech (TTS)

- **POST** `/v1/audio/speech`
- **Body**: JSON `{ "text": "Hello world" }`

```bash
curl -X POST 'http://localhost:8000/v1/audio/speech' \
  -H 'Content-Type: application/json' \
  -d '{ "text": "Hello from Talk" }' \
  -o out.mp3
```

### 3. LLM chat (vLLM / OpenAI API)

For chat, use the **LLM server via port 80** through the Talk nginx proxy.

- **Base URL:** `http://<host>/llm` (nginx proxies to the internal vLLM server)
- **Endpoint:** `POST {LLM_BASE}/v1/chat/completions`

Example:

```bash
LLM_BASE="http://localhost/llm"   # nginx on port 80 proxies to vLLM

curl -X POST "$LLM_BASE/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "model": "gemma3",
    "messages": [
      { "role": "system", "content": "You are a helpful assistant." },
      { "role": "user", "content": "Hello!" }
    ],
    "max_tokens": 128
  }'
```

Response shape follows the standard OpenAI chat completions format.

### 4. Speech‑to‑Speech

- **POST** `/v1/speech_to_speech`
- **Body**: `multipart/form-data` with `file`
- **Query**:
  - `language`: `kannada | hindi | tamil`
  - Optional `format=json` → JSON with transcription + LLM text + base64 audio.

```bash
curl -X POST 'http://localhost:8000/v1/speech_to_speech?language=kannada&format=json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'file=@kannada_sample.wav' |
  jq
```

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DWANI_API_BASE_URL_ASR` | Yes | ASR service URL (e.g. `http://host.docker.internal:10803` in Docker). |
| `DWANI_API_BASE_URL_TTS` | Yes | TTS service URL. |
| `DWANI_API_BASE_URL_LLM` | Yes | LLM service URL (OpenAI-compatible). |
| `DWANI_LLM_MODEL` | No | Model name (default: `gemma3`). |
| `DWANI_API_KEYS` | No | Comma-separated API keys. If set, public endpoints require `X-API-Key`. |

See [.env.example](.env.example) for optional timeouts, upload limits, and session context.
