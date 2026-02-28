import base64
import time
import os
import uuid
import asyncio

import argparse
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Form, Query
from pydantic import BaseModel, Field, ConfigDict

from fastapi.responses import RedirectResponse, StreamingResponse, Response, JSONResponse
from typing import List, Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks

import logging
import logging.config
from logging.handlers import RotatingFileHandler

from openai import AsyncOpenAI
from openai import APIError as OpenAIAPIError
import tempfile
from pathlib import Path
import httpx
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import uvicorn

# Config (env with defaults)
def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return int(v) if v else default

ASR_TIMEOUT = _env_int("DWANI_ASR_TIMEOUT", 30)
TTS_TIMEOUT = _env_int("DWANI_TTS_TIMEOUT", 30)
LLM_TIMEOUT = _env_int("DWANI_LLM_TIMEOUT", 60)
MAX_UPLOAD_BYTES = _env_int("DWANI_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)  # 25MB
MAX_RETRIES = _env_int("DWANI_MAX_RETRIES", 2)


logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "simple",
            "filename": "dwani_api.log",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "root": {
            "level": "INFO",
            "handlers": ["stdout", "file"],
        },
    },
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger("indic_all_server")


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# FastAPI app setup with enhanced docs
app = FastAPI(
    title="dwani.ai API",
    description="A multimodal Inference API designed for Privacy",
    version="1.0.0",
    redirect_slashes=False,
    openapi_tags=[
        {"name": "Chat", "description": "Chat-related endpoints"},
        {"name": "Audio", "description": "Audio processing and TTS endpoints"},
        {"name": "Translation", "description": "Text translation endpoints"},
    ],
)
app.state.limiter = limiter


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    resp = _error_response(429, "Rate limit exceeded. Try again later.", rid, {"detail": str(getattr(exc, "detail", ""))})
    resp.headers["Retry-After"] = "60"
    return resp
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ 
        "https://dwani.ai",
        "https://*.dwani.ai",
        "https://dwani-*.hf.space",
        "http://localhost:11080"
        ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(status_code: int, message: str, request_id: str = "", details: Optional[Dict] = None) -> JSONResponse:
    rid = request_id or str(uuid.uuid4())
    body = {
        "error": {
            "code": str(status_code),
            "message": message,
            "request_id": rid,
            "details": details or {},
        },
        "detail": message,  # backward compat for clients expecting FastAPI default
    }
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _error_response(exc.status_code, detail, request_id)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get(
    "/v1/warehouse/state",
    summary="Get warehouse robots and items state",
    description="Proxy endpoint that returns the current simulated warehouse state (robots, items, bounds) for visualization.",
    tags=["Warehouse"],
)
@limiter.limit("60/minute")
async def get_warehouse_state(request: Request) -> Dict[str, Any]:
    """Fetch warehouse state from the agents service."""
    agent_base = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
    if not agent_base:
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    url = f"{agent_base}/v1/warehouse/state"
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.get(url)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Warehouse state request failed: {exc}")
        raise HTTPException(status_code=502, detail="Failed to reach warehouse state service") from exc
    if resp.status_code != 200:
        logger.error(f"Warehouse state service returned {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=502, detail="Warehouse state service returned an error")
    data = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Warehouse state service returned invalid data")
    return data


class WarehouseCommandRequest(BaseModel):
    robot: str = Field(..., description="Robot to control: 'uav', 'ugv', or 'arm'.")
    direction: str | None = Field(default=None, description="Direction: north, south, east, or west.")
    x: float | None = Field(default=None)
    y: float | None = Field(default=None)
    z: float | None = Field(default=None)


@app.post(
    "/v1/warehouse/command",
    summary="Send a deterministic warehouse command",
    description="Directly update warehouse robot positions via the agents service.",
    tags=["Warehouse"],
)
@limiter.limit("60/minute")
async def proxy_warehouse_command(request: Request, body: WarehouseCommandRequest) -> Dict[str, Any]:
    agent_base = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
    if not agent_base:
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    url = f"{agent_base}/v1/warehouse/command"
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(url, json=body.model_dump())
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Warehouse command request failed: {exc}")
        raise HTTPException(status_code=502, detail="Failed to reach warehouse command service") from exc
    if resp.status_code != 200:
        logger.error(f"Warehouse command service returned {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=502, detail="Warehouse command service returned an error")
    data = resp.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Warehouse command service returned invalid data")
    return data


@app.get("/health", tags=["Health"])
async def health() -> Dict[str, str]:
    """Liveness: service is running."""
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready() -> Dict[str, Any]:
    """Readiness: dependencies (ASR, TTS, LLM) are reachable."""
    checks = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in [
            ("asr", os.getenv("DWANI_API_BASE_URL_ASR", "").rstrip("/") + "/" if os.getenv("DWANI_API_BASE_URL_ASR") else None),
            ("tts", os.getenv("DWANI_API_BASE_URL_TTS", "").rstrip("/") + "/" if os.getenv("DWANI_API_BASE_URL_TTS") else None),
            ("llm", os.getenv("DWANI_API_BASE_URL_LLM", "").rstrip("/") + "/v1/models" if os.getenv("DWANI_API_BASE_URL_LLM") else None),
        ]:
            if not url:
                checks[name] = "skipped (no url)"
                continue
            try:
                r = await client.get(url)
                checks[name] = "ok" if r.status_code < 500 else f"error {r.status_code}"
            except Exception as e:
                checks[name] = f"unreachable: {type(e).__name__}"
    return {"status": "ok" if all("ok" in str(v) or "skipped" in str(v) for v in checks.values()) else "degraded", "checks": checks}


class TranscriptionResponse(BaseModel):
    text: str = Field(..., description="Transcribed text from the audio")

    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "Hello, how are you?"}}
    )

async def _retry_async(coro_fn, max_retries: int = MAX_RETRIES):
    """Execute async call with exponential backoff retries."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except HTTPException:
            raise  # Don't retry HTTP errors
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_err = e
            if attempt < max_retries:
                delay = 2**attempt
                logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay}s: {e}")
                await asyncio.sleep(delay)
    raise last_err


async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: str = Query(..., description="Language of the audio (kannada, hindi, tamil, english, german)")
):
    # Validate language
    allowed_languages = ["kannada", "hindi", "tamil", "english", "german", "telugu", "marathi"]
    if language not in allowed_languages:
        raise HTTPException(status_code=400, detail=f"Language must be one of {allowed_languages}")

    start_time = time.time()
    file_content = await file.read()
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")

    if language in ["english", "german"]:
        base = os.getenv("DWANI_API_BASE_URL_TRANSCRIPTION", "http://localhost:8000").rstrip("/")
        url = f"{base}/v1/audio/transcriptions"
        files = {"file": (file.filename, file_content, file.content_type), "model": (None, "Systran/faster-whisper-small")}

        async def _do():
            async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
                r = await client.post(url, files=files)
                if r.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Transcription failed: {r.text or r.status_code}")
                data = r.json()
                text = data.get("text", "")
                if not text:
                    raise HTTPException(status_code=500, detail="Transcription failed: empty result")
                return TranscriptionResponse(text=text)

        try:
            result = await _retry_async(_do)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Transcription request failed: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
        logger.debug(f"Transcription completed in {time.time() - start_time:.2f}s")
        return result
    else:
        external_url = f"{os.getenv('DWANI_API_BASE_URL_ASR')}/transcribe/?language={language}"
        files = {"file": (file.filename, file_content, file.content_type)}

        async def _do():
            async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
                r = await client.post(external_url, files=files, headers={"accept": "application/json"})
                r.raise_for_status()
                return TranscriptionResponse(text=r.json().get("text", "") or "")

        try:
            result = await _retry_async(_do)
        except httpx.TimeoutException:
            logger.error("Transcription service timed out")
            raise HTTPException(status_code=504, detail="Transcription service timeout")
        except httpx.HTTPStatusError as e:
            logger.error(f"Transcription HTTP error: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Transcription request failed: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
        logger.debug(f"Transcription completed in {time.time() - start_time:.2f}s")
        return result

# LLM (OpenAI-compatible, e.g. Gemma3)
LLM_MODEL = os.getenv("DWANI_LLM_MODEL", "gemma3")
AGENT_BASE_URL = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
SESSION_CONTEXT_LIMIT = _env_int("DWANI_SESSION_CONTEXT_LIMIT", 10)  # max messages (5 turns) to send as context
SESSION_MAX_HISTORY = _env_int("DWANI_SESSION_MAX_HISTORY", 20)  # max messages to store per session

# In-memory session store: session_id -> list of {role, content}
_session_store: Dict[str, List[Dict[str, str]]] = {}
_session_order: List[str] = []
_MAX_SESSIONS = 5000


def _get_session_context(session_id: str) -> List[Dict[str, str]]:
    if not session_id:
        return []
    history = _session_store.get(session_id, [])
    return history[-SESSION_CONTEXT_LIMIT:]


def _append_to_session(session_id: str, user: str, assistant: str) -> None:
    if not session_id:
        return
    if session_id not in _session_store:
        _session_store[session_id] = []
        _session_order.append(session_id)
        while len(_session_store) > _MAX_SESSIONS and _session_order:
            old = _session_order.pop(0)
            _session_store.pop(old, None)
    history = _session_store[session_id]
    history.append({"role": "user", "content": user})
    history.append({"role": "assistant", "content": assistant})
    if len(history) > SESSION_MAX_HISTORY:
        _session_store[session_id] = history[-SESSION_MAX_HISTORY:]


async def call_llm(user_text: str, context: Optional[List[Dict[str, str]]] = None) -> str:
    """Send text to OpenAI-compatible LLM with optional conversation context."""
    base_url = os.getenv("DWANI_API_BASE_URL_LLM", "").rstrip("/")
    if not base_url:
        raise ValueError("DWANI_API_BASE_URL_LLM is not set")
    api_base = f"{base_url}/v1" if not base_url.endswith("/v1") else base_url
    messages = [
        {"role": "system", "content": "You must respond in at most one line. Keep your reply to a single short sentence. Maintain conversation context when given previous messages."},
    ]
    if context:
        messages.extend(context)
    messages.append({"role": "user", "content": user_text})
    try:
        client = AsyncOpenAI(base_url=api_base, api_key="dummy", timeout=httpx.Timeout(LLM_TIMEOUT))
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=256,
        )
    except OpenAIAPIError as e:
        logger.error(f"LLM API error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")
    content = response.choices[0].message.content if response.choices else None
    if not content or not str(content).strip():
        raise HTTPException(status_code=502, detail="LLM returned empty response")
    return " ".join(str(content).strip().split())


async def call_agent(agent_name: str, user_text: str, session_id: Optional[str]) -> str:
    """Send text to the agents service for a named agent."""
    if not AGENT_BASE_URL:
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    if not session_id:
        raise HTTPException(status_code=400, detail="Agent mode requires a session_id")

    url = f"{AGENT_BASE_URL}/v1/agents/{agent_name}/chat"
    payload = {"session_id": session_id, "message": user_text}
    async def _do():
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            return await client.post(url, json=payload)

    try:
        resp = await _retry_async(_do)
    except Exception as e:
        logger.error(f"Agent service request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Agent service error: {str(e)}")

    if resp.status_code != 200:
        logger.error(f"Agent service returned {resp.status_code}: {resp.text}")
        raise HTTPException(status_code=502, detail="Agent service returned an error")

    data = resp.json()
    reply = data.get("reply")
    if not reply or not str(reply).strip():
        raise HTTPException(status_code=502, detail="Agent returned empty response")
    return " ".join(str(reply).strip().split())


from enum import Enum

class SupportedLanguage(str, Enum):
    kannada = "kannada"
    hindi = "hindi"
    tamil = "tamil"


class ChatRequest(BaseModel):
    text: str = Field(..., description="User message text")
    mode: str = Field("llm", description="Processing mode: 'llm' or 'agent'")
    agent_name: Optional[str] = Field(
        None, description="Agent name when mode='agent' (defaults to 'travel_planner')"
    )


@app.post(
    "/v1/chat",
    summary="Text chat",
    description="Send a text message and receive an LLM or agent reply, with session-based context.",
    tags=["Chat"],
)
@limiter.limit("60/minute")
async def chat(request: Request, payload: ChatRequest) -> Dict[str, str]:
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text must not be empty")

    session_id = (request.headers.get("X-Session-ID") or "").strip() or None
    context = _get_session_context(session_id) if session_id else []

    if payload.mode == "agent":
        selected_agent = payload.agent_name or "travel_planner"
        reply = await call_agent(selected_agent, text, session_id=session_id)
    else:
        reply = await call_llm(text, context=context)

    if session_id:
        _append_to_session(session_id, text, reply)

    return {"user": text, "reply": reply}


@app.post("/v1/speech_to_speech",
          summary="Speech-to-Speech Conversion",
          description="Convert input speech to processed speech in the specified language by calling an external speech-to-speech API.",
          tags=["Audio"],
          responses={
              200: {"description": "Audio stream", "content": {"audio/mp3": {"example": "Binary audio data"}}},
              400: {"description": "Invalid input or language"},
              413: {"description": "File too large"},
              429: {"description": "Rate limit exceeded"},
              504: {"description": "External API timeout"},
              500: {"description": "External API error"}
          })
@limiter.limit("20/minute")
async def speech_to_speech(
    request: Request,
    file: UploadFile = File(..., description="Audio file to process"),
    language: str = Query(..., description="Language of the audio (kannada, hindi, tamil)"),
    mode: str = Query("llm", description="Processing mode: 'llm' or 'agent'"),
    agent_name: Optional[str] = Query(None, description="Agent name when mode='agent'"),
) -> Response:
    # Validate language
    allowed_languages = [lang.value for lang in SupportedLanguage]
    if language not in allowed_languages:
        raise HTTPException(status_code=400, detail=f"Language must be one of {allowed_languages}")
    
    logger.debug("Processing speech-to-speech request", extra={
        "endpoint": "/v1/speech_to_speech",
        "audio_filename": file.filename,
        "language": language,
        "client_ip": getattr(request.client, "host", None)
    })

    try:
        session_id = (request.headers.get("X-Session-ID") or "").strip() or None
        context = _get_session_context(session_id) if session_id else []

        asr_text = await transcribe_audio(file=file, language=language)
        text = asr_text.text
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="No speech detected in the audio")

        if mode == "agent":
            selected_agent = agent_name or "travel_planner"
            llm_text = await call_agent(selected_agent, text, session_id=session_id)
        else:
            llm_text = await call_llm(text, context=context)

        if not llm_text or not llm_text.strip():
            raise HTTPException(status_code=502, detail="Text for TTS is empty")

        if session_id:
            _append_to_session(session_id, text, llm_text)

        base_url = f"{os.getenv('DWANI_API_BASE_URL_TTS')}/v1/audio/speech"
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
            tts_response = await client.post(
                base_url,
                json={"text": llm_text},
                headers={"accept": "*/*", "Content-Type": "application/json"},
            )
            tts_response.raise_for_status()
            audio_bytes = tts_response.content

        if not audio_bytes or len(audio_bytes) == 0:
            logger.error(
                "TTS returned empty audio",
                extra={"base_url": base_url, "status_code": tts_response.status_code},
            )
            raise HTTPException(
                status_code=502,
                detail="TTS service returned empty audio; no MP3 data received",
            )

        logger.info(
            "TTS audio received",
            extra={"content_length": len(audio_bytes), "content_type": tts_response.headers.get("Content-Type")},
        )

        return_json = request.query_params.get("format") == "json"
        if return_json:
            from fastapi.responses import JSONResponse
            return JSONResponse(content={
                "transcription": text,
                "llm_response": llm_text,
                "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            })
        headers = {
            "Content-Disposition": "inline; filename=\"speech.mp3\"",
            "Cache-Control": "no-cache",
            "Content-Type": "audio/mp3",
        }
        return Response(content=audio_bytes, media_type="audio/mp3", headers=headers)
    except httpx.TimeoutException:
        logger.error("External speech-to-speech API timed out")
        raise HTTPException(status_code=504, detail="External API timeout")
    except httpx.HTTPError as e:
        logger.error(f"External speech-to-speech API error: {e}")
        raise HTTPException(status_code=502, detail=f"External API error: {str(e)}")
    


if __name__ == "__main__":
    
    external_api_base_url_llm = os.getenv("DWANI_API_BASE_URL_LLM")
    if not external_api_base_url_llm:
        raise ValueError("Environment variable DWANI_API_BASE_URL_LLM must be set")
    
    
    external_api_base_url_tts = os.getenv("DWANI_API_BASE_URL_TTS")
    if not external_api_base_url_tts:
        raise ValueError("Environment variable DWANI_API_BASE_URL_TTS must be set")
    
    external_api_base_url_asr = os.getenv("DWANI_API_BASE_URL_ASR")
    if not external_api_base_url_asr:
        raise ValueError("Environment variable DWANI_API_BASE_URL_ASR must be set")
    
    
    parser = argparse.ArgumentParser(description="Run the FastAPI server.")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on.")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)