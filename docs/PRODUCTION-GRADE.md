# Making Talk Production-Grade

This document suggests improvements to take the Talk system (backend, agents, UI, deployment) to production quality. It builds on [IMPROVEMENTS.md](IMPROVEMENTS.md) and focuses on reliability, observability, security, and operability.

---

## 1. Reliability & Resilience

### 1.1 Backend (talk-server)

- **Request ID propagation**  
  Propagate `X-Request-ID` (or generate one) to outbound calls (ASR, TTS, LLM, agents) so logs can be correlated across services.

- **Circuit breaker / fallbacks**  
  If ASR or TTS is repeatedly failing, consider failing fast or returning a clear “service unavailable” instead of long timeouts. Optional: short circuit after N consecutive failures per endpoint.

- **Graceful shutdown**  
  On SIGTERM, stop accepting new requests, finish in-flight requests (with a timeout), then exit so orchestrators get clean restarts.

### 1.2 Agents service

- **Readiness probe**  
  Add `GET /ready` that checks LiteLLM/LLM reachability (e.g. simple completion or `models` list). Use it in Docker/K8s so traffic is sent only when the agent can call the model.

- **Session persistence**  
  Replace or complement `InMemorySessionService` with a persistent store (Redis, Postgres, or ADK-compatible session backend) so agent conversations survive restarts and scale across replicas.

- **Timeouts and limits**  
  Enforce a max duration per agent run and a max message length for `body.message` to avoid runaway LLM calls and abuse.

- **Health in compose**  
  Add a `healthcheck` for the `agents` service in all compose files (e.g. `GET http://agents:8081/healthz`) and `depends_on: agents` with `condition: service_healthy` for `talk` where appropriate.

### 1.3 UI

- **Retry on failure**  
  Add an explicit “Retry” for failed requests (speech-to-speech and chat) so users can recover from transient errors without losing context.

- **Request timeout handling**  
  Treat client-side timeouts (e.g. 60s) as a clear “Request took too long; please try again” and allow retry.

- **Offline detection**  
  Use `navigator.onLine` and/or fetch failure to show a short “You appear offline” message and disable send/mic until back online.

---

## 2. Observability

### 2.1 Structured logging

- **JSON logs in production**  
  Use a JSON formatter (e.g. `python-json-logger`) with fields: `timestamp`, `level`, `message`, `request_id`, `agent_name` (when applicable), `session_id` (hashed or redacted if needed). Makes ingestion into Datadog/Loki/CloudWatch straightforward.

- **Structured fields in agents**  
  In `agents/service_main.py`, log `agent_name`, `session_id` (or hash), and success/failure per request so you can trace and debug viva vs travel flows.

### 2.2 Metrics

- **Prometheus metrics**  
  Expose `/metrics` (e.g. with `prometheus-fastapi-instrumentator`) for:
  - Request count by endpoint, method, status.
  - Request latency (histogram) for `/v1/speech_to_speech`, `/v1/chat`, and agents’ `/v1/agents/{agent_name}/chat`.
  - Counts for 4xx/5xx and timeouts.

- **Agent-specific metrics**  
  Optional: counters or histograms per `agent_name` (e.g. `viva_examiner`, `travel_planner`) for latency and errors so you can compare and alert per agent.

### 2.3 Tracing (optional)

- **OpenTelemetry**  
  Add OTel for HTTP and (if available) for LLM/agent spans so a single request can be traced: talk-server → agents → LLM, and talk-server → ASR/TTS.

---

## 3. Security

### 3.1 Backend and agents

- **Input validation**  
  - Already: upload size, language allowlist.  
  - Add: validate `agent_name` against a known list (e.g. `travel_planner`, `viva_examiner`) before calling the agents service to avoid path confusion.  
  - Enforce max length on chat text and session_id.

- **CORS**  
  Avoid `allow_origins=["*"]` in production for the agents service. Restrict to the same origins as the main API (e.g. `talk.dwani.ai`) or configure via env.

- **Secrets**  
  Keep using env (or a secret manager) for `LITELLM_API_KEY`, `HF_TOKEN`, etc. Never log or expose them. Document in runbooks where they are set (e.g. compose, K8s secrets).

### 3.2 API authentication (optional)

- **Optional API key**  
  For server-to-server or power users, support an `Authorization: Bearer <token>` or `X-API-Key` and rate-limit per key. Keep the current unauthenticated flow for the main UI if desired.

---

## 4. Testing

### 4.1 CI

- **Backend tests from correct directory**  
  Run backend tests from `talk-server` with `talk-server/requirements.txt` (e.g. `cd talk-server && pip install -r requirements.txt && pytest -q`) so CI doesn’t depend on a root `requirements.txt` and matches local runs.

- **Agents service tests**  
  Add a small test suite for `agents/service_main.py`: e.g. `GET /healthz`, and `POST /v1/agents/viva_examiner/chat` (and travel_planner) with mocked Runner or a test agent that returns a fixed string. Run in CI.

- **Smoke test**  
  Optional: a CI job that starts the stack (e.g. `compose up` with mock or minimal services), calls `GET /health` and `GET /ready`, and optionally `POST /v1/chat` with `mode=agent&agent_name=viva_examiner` and checks for a non-empty reply.

### 4.2 Backend coverage

- **Critical paths**  
  Add tests for: `speech_to_speech` (with mocked ASR/LLM/TTS), `chat` (LLM and agent modes), error paths (timeout, 502, empty body). Use pytest and mocks so CI stays fast and deterministic.

---

## 5. Deployment & Operations

### 5.1 Compose and orchestration

- **Agents healthcheck**  
  In every compose file that includes `agents`, add:
  ```yaml
  agents:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
  ```
  and have `talk` depend on `agents` with `condition: service_healthy` when in agent mode.

- **Resource limits**  
  Set `deploy.resources.limits` (memory, CPU) for `talk`, `agents`, and UI so a single service cannot starve others.

- **Restart policy**  
  Already using `restart: unless-stopped`; in K8s use equivalent (e.g. `Always` with backOff).

### 5.2 Runbooks

- **docs/runbook.md**  
  Add a short runbook with:
  - How to check health of talk, agents, ASR, TTS, LLM.
  - Common failures: 504 (timeout), 502 (agent/LLM down), empty transcription (ASR).
  - Where logs live (stdout, file paths if any).
  - How to restart or scale agents/talk.
  - Env vars that must be set for production (see .env.example and README).

### 5.3 Versioning and releases

- **API versioning**  
  Keep `/v1/` and document that new backward-compatible options go under `/v1/`; breaking changes get a new path (e.g. `/v2/`) with a deprecation window.

- **Image tags**  
  Prefer tagged images (e.g. `dwani/talk-server:1.2.3`) in addition to `latest` so production can pin versions and roll back cleanly.

---

## 6. Product & UX (production polish)

### 6.1 Conversation persistence

- **Persist conversations**  
  Persist the conversations list in `localStorage` (or IndexedDB) keyed by session so refresh doesn’t lose history. Cap size (e.g. last 50) and offer “Clear history.”

### 6.2 Progress and errors

- **Step-wise progress**  
  For speech-to-speech, show steps like “Transcribing…”, “Thinking…”, “Speaking…” so users know the system is working during long runs.

- **Clear error messages**  
  Map common backend errors (429, 502, 504) to user-friendly copy (e.g. “Too many requests; try again in a minute”, “Service temporarily unavailable”, “Request timed out”) and keep a “Retry” action.

### 6.3 Accessibility and mobile

- **a11y**  
  Ensure status and errors are announced (e.g. `aria-live`), keyboard navigation works, and focus is visible. Test with a screen reader.

- **Mobile**  
  Test on small viewports; ensure mic button and sidebar are easy to use on touch devices.

---

## 7. Viva examiner–specific

- **Scoring consistency**  
  In the agent instruction, reference a simple rubric (e.g. 0–3 poor, 4–6 partial, 7–8 good, 9–10 excellent) so scores are more consistent across sessions and models.

- **Rate limit**  
  Consider a slightly stricter rate limit for agent endpoints (e.g. viva) to avoid cost spikes from automated or repeated runs.

- **Session hygiene**  
  Document that starting a “New conversation” is recommended when switching between agents (travel vs viva) so session state doesn’t mix.

---

## 8. Suggested priority

| Priority | Area              | Actions                                              |
|----------|-------------------|------------------------------------------------------|
| P0       | Reliability       | Agents readiness probe; healthchecks in compose; retry + timeout in UI |
| P1       | Observability     | Structured logging; Prometheus metrics; request_id propagation |
| P1       | Testing           | CI runs backend tests from talk-server; add agents health + smoke tests |
| P2       | Security          | Validate agent_name; tighten CORS; optional API key |
| P2       | Ops               | Runbook; resource limits; image tags                |
| P3       | Sessions          | Persistent session store for agents                  |
| P3       | UX                | Conversation persistence; step-wise progress; a11y   |

Implementing P0 and P1 gives a solid production baseline; P2–P3 can follow as traffic and requirements grow.
