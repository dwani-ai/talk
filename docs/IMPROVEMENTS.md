# Talk Project — Improvement Plan

Detailed steps to improve the Talk (speech-to-speech) project across backend, frontend, DevOps, and product.

---

## 1. Backend (Python / FastAPI)

### 1.1 Async HTTP clients
**Problem:** `requests` is synchronous and blocks the event loop during ASR/TTS calls.  
**Steps:**
1. Replace `requests.post()` with `httpx.AsyncClient()` for ASR and TTS.
2. Use `await client.post(...)` in `transcribe_audio` and `speech_to_speech`.
3. Add `httpx` to `requirements.txt` if not present.
4. Run ASR and TTS calls with `async/await` to avoid blocking under load.

### 1.2 Configurable transcription URL
**Problem:** English/German transcription uses hardcoded `http://localhost:8000/v1/audio/transcriptions`.  
**Steps:**
1. Add env var `DWANI_API_BASE_URL_TRANSCRIPTION` (or reuse an existing base).
2. Replace the hardcoded URL with `f"{base}/v1/audio/transcriptions"`.
3. Document in `.env.example` and README.

### 1.3 Health checks
**Problem:** No readiness/liveness endpoints for orchestration.  
**Steps:**
1. Add `GET /health` returning `{"status": "ok"}`.
2. Add `GET /ready` that checks ASR/TTS/LLM reachability (optional).
3. Use these in Docker/K8s health checks.

### 1.4 Request timeouts and retries
**Problem:** Single timeout; no retries for transient failures.  
**Steps:**
1. Make timeouts configurable via env (e.g. `DWANI_ASR_TIMEOUT`, `DWANI_LLM_TIMEOUT`).
2. Add retries with backoff for ASR/TTS/LLM (e.g. 2 retries, exponential backoff).
3. Log retries and failures for debugging.

### 1.5 Structured error responses
**Problem:** Error format varies; clients may struggle to parse.  
**Steps:**
1. Define a shared error schema: `{ "error": { "code": "...", "message": "...", "details": {} } }`.
2. Use FastAPI exception handlers to return this format consistently.
3. Include request ID in errors for tracing.

### 1.6 Rate limiting
**Problem:** No protection against abuse or overload.  
**Steps:**
1. Add rate limiting (e.g. `slowapi` or custom middleware).
2. Limit by IP or API key: e.g. 10 req/min per IP.
3. Return 429 with `Retry-After` header when exceeded.

---

## 2. Frontend (React / talk-ui)

### 2.1 Conversation persistence
**Problem:** Conversations are lost on refresh.  
**Steps:**
1. Persist `conversations` in `localStorage` (or IndexedDB for large histories).
2. Load on mount; save on each new entry.
3. Add a “Clear history” action.
4. Optional: cap stored items (e.g. last 50).

### 2.2 Export conversations
**Problem:** No way to export or share logs.  
**Steps:**
1. Add “Export” in the sidebar (JSON or plain text).
2. Add “Copy” for a single exchange.
3. Optional: export as Markdown for notes.

### 2.3 Accessibility (a11y)
**Problem:** Limited keyboard and screen-reader support.  
**Steps:**
1. Add `aria-live` regions for status and errors.
2. Ensure full keyboard navigation (Tab, Enter, Escape).
3. Add visible focus styles.
4. Test with a screen reader (e.g. NVDA, VoiceOver).

### 2.4 Offline / error recovery
**Problem:** Network errors are shown but not retried.  
**Steps:**
1. Add “Retry” for failed requests.
2. Show a clear offline indicator when `navigator.onLine` is false.
3. Optional: queue failed requests and retry when back online.

### 2.5 Loading and progress
**Problem:** Long ASR→LLM→TTS flow with no progress feedback.  
**Steps:**
1. Show step-wise progress: “Transcribing…”, “Thinking…”, “Generating speech…”.
2. Use a progress bar or spinner per step.
3. Optional: backend streaming or status endpoint for finer progress.

### 2.6 Mobile UX
**Problem:** Layout may not be ideal on small screens.  
**Steps:**
1. Test on mobile viewports (320px–428px).
2. Make the mic button larger and easier to tap.
3. Ensure sidebar works well on mobile (full-screen overlay).
4. Consider touch-specific events for push-to-talk.

---

## 3. DevOps & Deployment

### 3.1 Single compose for full stack
**Problem:** TTS, ASR, LLM are run separately; setup is fragmented.  
**Steps:**
1. Create `compose.full.yml` with services: `talk`, `talk-ui`, `asr`, `tts`, `llm`.
2. Use `docs/text-qwen-llama-cpp.yml` and `vllm.yml` as references.
3. Add a `Makefile` or `scripts/run-full.sh` to start everything.
4. Document in README as “Full local stack”.

### 3.2 Health checks in compose
**Problem:** Containers can start before dependencies are ready.  
**Steps:**
1. Add `healthcheck` to `talk` (e.g. `curl /health`).
2. Add `depends_on` with `condition: service_healthy` for `talk-ui` if needed.
3. Add health checks for ASR/TTS/LLM services when they are in compose.

### 3.3 Secrets management
**Problem:** API keys and URLs in `.env` can be committed.  
**Steps:**
1. Use Docker secrets or a vault for production.
2. Add `.env` to `.gitignore` if not already.
3. Document required env vars in `.env.example` with placeholders.

### 3.4 CI/CD
**Problem:** No automated tests or deployment pipeline.  
**Steps:**
1. Add GitHub Actions (or similar) workflow:
   - Lint (ruff, eslint).
   - Unit tests for backend (pytest) and frontend (vitest).
   - Build Docker images.
   - Optional: deploy to staging on merge.
2. Add a smoke test that hits `/health` and `/v1/speech_to_speech` with a sample file.

### 3.5 Observability
**Problem:** Limited visibility into runtime behavior.  
**Steps:**
1. Add structured logging (JSON) with request IDs.
2. Add Prometheus metrics: request count, latency, error rate.
3. Optional: OpenTelemetry for traces across ASR → LLM → TTS.

---

## 4. API & Product

### 4.1 Conversation context
**Problem:** Each request is stateless; no multi-turn context.  
**Steps:**
1. Add optional `session_id` or `conversation_id` header/param.
2. Store recent exchanges per session (in-memory or Redis).
3. Send last N turns as context to the LLM.
4. Document session behavior in the API spec.

### 4.2 Streaming TTS
**Problem:** User waits for full TTS before playback.  
**Steps:**
1. Add streaming endpoint (e.g. `?stream=1`) that returns chunked audio.
2. Use `StreamingResponse` with TTS chunks.
3. Update UI to play chunks as they arrive (e.g. MediaSource API).

### 4.3 WebSocket for real-time
**Problem:** Request/response only; no continuous conversation mode.  
**Steps:**
1. Add WebSocket endpoint for bidirectional audio.
2. Client streams audio; server streams transcription + LLM + TTS.
3. Reduces latency for back-and-forth conversations.

### 4.4 API versioning
**Problem:** Breaking changes would affect all clients.  
**Steps:**
1. Keep `/v1/` prefix; plan `/v2/` for future.
2. Document deprecation policy (e.g. 6 months notice).
3. Add `X-API-Version` header in responses.

### 4.5 Usage analytics (privacy-preserving)
**Problem:** No insight into usage patterns.  
**Steps:**
1. Log anonymized metrics: language, latency, success/failure.
2. Avoid logging PII or audio content.
3. Optional: dashboard for admins.

---

## 5. Testing

### 5.1 Backend tests
**Steps:**
1. Add `tests/` with `conftest.py` (pytest fixtures).
2. Mock ASR, LLM, TTS responses.
3. Test `speech_to_speech` with sample audio file.
4. Test error paths (timeout, 500, empty response).
5. Run with `pytest tests/ -v`.

### 5.2 Frontend tests
**Steps:**
1. Add Vitest and React Testing Library.
2. Test App: render, language change, mic button states.
3. Mock `fetch` for API responses.
4. Add a basic E2E test (e.g. Playwright) for the full flow.

### 5.3 Integration tests
**Steps:**
1. Use `kannada_sample.wav` against a real or mocked backend.
2. Assert response is valid MP3 and JSON when `format=json`.
3. Run in CI against a test compose stack.

---

## 6. Documentation

### 6.1 API documentation
**Steps:**
1. Ensure OpenAPI/Swagger is complete (all params, responses, errors).
2. Add example requests/responses for each endpoint.
3. Document `format=json` and session/streaming options.

### 6.2 Architecture diagram
**Steps:**
1. Create `docs/architecture.md` with a diagram (Mermaid or image).
2. Show: Browser → talk-ui → talk → ASR, LLM, TTS.
3. Document data flow and env vars.

### 6.3 Runbooks
**Steps:**
1. Add `docs/runbook.md` for common issues:
   - 504 timeout → increase nginx/backend timeouts.
   - Connection refused → check host.docker.internal, ports.
   - Empty transcription → ASR service health.
2. Include log locations and how to debug.

---

## 7. Security

### 7.1 Input validation
**Steps:**
1. Limit upload size (e.g. 25MB) in FastAPI.
2. Validate file type (audio only) before processing.
3. Sanitize language param against an allowlist.

### 7.2 CORS tightening
**Problem:** `allow_origins` may be too permissive.  
**Steps:**
1. Restrict to known domains (e.g. talk.dwani.ai, localhost).
2. Avoid `*` in production.
3. Make CORS configurable via env.

### 7.3 API authentication (optional)
**Steps:**
1. Add optional API key auth via header.
2. Rate limit per key.
3. Document in API docs.

---

## 8. Suggested Priority Order

| Priority | Area              | Items                                      | Effort  |
|----------|-------------------|--------------------------------------------|---------|
| P0       | Reliability        | Health checks, timeouts, error handling     | 1–2 days|
| P0       | UX                 | Conversation persistence, retry on error   | 1 day   |
| P1       | Performance        | Async HTTP, streaming TTS                   | 2–3 days|
| P1       | DevOps             | Full compose, CI smoke tests                | 1–2 days|
| P2       | Product            | Session context, WebSocket                  | 3–5 days|
| P2       | Testing            | Backend + frontend tests                    | 2–3 days|
| P3       | Observability      | Metrics, structured logs                   | 1–2 days|
| P3       | Security           | Input validation, CORS, optional auth      | 1 day   |

---

## 9. Quick Wins (can do today)

1. Add `GET /health` returning `{"status": "ok"}`.
2. Persist conversations in `localStorage`.
3. Add “Retry” button when a request fails.
4. Add `client_max_body_size` and upload limit in backend.
5. Add `scripts/run-full.sh` that starts all services with one command.
