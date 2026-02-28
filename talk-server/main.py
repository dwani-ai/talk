import argparse
import os
import uuid
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import logger
from deps import limiter
from routers import chat, chess, health, warehouse

# App
app = FastAPI(
    title="dwani.ai API",
    description="Conversational AI Agents for Indian languages — speech-to-speech, agents, and multimodal inference.",
    version="1.0.0",
    redirect_slashes=False,
    openapi_tags=[
        {"name": "Chat", "description": "Chat-related endpoints"},
        {"name": "Audio", "description": "Audio processing and TTS endpoints"},
        {"name": "Translation", "description": "Text translation endpoints"},
        {"name": "Warehouse", "description": "Warehouse simulation endpoints"},
        {"name": "Chess", "description": "Chess gameplay endpoints"},
    ],
)
app.state.limiter = limiter


def _setup_tracing() -> None:
    if os.getenv("DWANI_ENABLE_TRACING", "0") != "1":
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv("DWANI_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() or None
        tracer_provider = TracerProvider(resource=Resource.create({"service.name": "talk-server"}))
        span_exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        logger.warning("Tracing setup skipped due to error: %s", exc)


def _setup_metrics() -> None:
    if os.getenv("DWANI_ENABLE_METRICS", "1") != "1":
        return
    Instrumentator(excluded_handlers=["/health"]).instrument(app).expose(app, endpoint="/metrics")


_setup_tracing()
_setup_metrics()


@app.on_event("startup")
async def validate_required_env() -> None:
    if os.getenv("DWANI_ENFORCE_ENV", "0") != "1":
        return
    required = [
        "DWANI_API_BASE_URL_LLM",
        "DWANI_API_BASE_URL_TTS",
        "DWANI_API_BASE_URL_ASR",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def _error_response(status_code: int, message: str, request_id: str = "", details: Optional[Dict] = None) -> JSONResponse:
    rid = request_id or str(uuid.uuid4())
    body = {
        "error": {
            "code": str(status_code),
            "message": message,
            "request_id": rid,
            "details": details or {},
        },
        "detail": message,
    }
    return JSONResponse(status_code=status_code, content=body)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    rid = getattr(request.state, "request_id", str(uuid.uuid4()))
    resp = _error_response(429, "Rate limit exceeded. Try again later.", rid, {"detail": str(getattr(exc, "detail", ""))})
    resp.headers["Retry-After"] = "60"
    return resp


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _error_response(exc.status_code, detail, request_id)


# CORS
_CORS_EXPLICIT_ORIGINS = [
    "https://dwani.ai",
    "https://talk.dwani.ai",
    "http://localhost:11080",
    "http://localhost:5173",
    "http://localhost",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:80",
]


def _cors_allow_origin(origin: Optional[str]) -> bool:
    if not origin:
        return False
    if origin in _CORS_EXPLICIT_ORIGINS:
        return True
    if origin.startswith("https://") and origin.endswith(".dwani.ai"):
        return True
    if "dwani-" in origin and ".hf.space" in origin and origin.startswith("https://"):
        return True
    return False


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS" and _cors_allow_origin(origin):
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS, HEAD",
                "Access-Control-Allow-Headers": "Content-Type, X-Session-ID, X-Request-ID",
                "Access-Control-Max-Age": "86400",
            },
        )
    response = await call_next(request)
    if _cors_allow_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, HEAD"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Session-ID, X-Request-ID"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_EXPLICIT_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Routers
app.include_router(health.router)
app.include_router(warehouse.router)
app.include_router(chess.router)
app.include_router(chat.router)


if __name__ == "__main__":
    if not os.getenv("DWANI_API_BASE_URL_LLM"):
        raise ValueError("Environment variable DWANI_API_BASE_URL_LLM must be set")
    if not os.getenv("DWANI_API_BASE_URL_TTS"):
        raise ValueError("Environment variable DWANI_API_BASE_URL_TTS must be set")
    if not os.getenv("DWANI_API_BASE_URL_ASR"):
        raise ValueError("Environment variable DWANI_API_BASE_URL_ASR must be set")

    parser = argparse.ArgumentParser(description="Run the FastAPI server.")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on.")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
