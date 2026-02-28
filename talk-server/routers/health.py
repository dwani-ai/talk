import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> Dict[str, str]:
    """Liveness: service is running."""
    return {"status": "ok"}


@router.get("/ready")
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
