import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Request

from config import LLM_TIMEOUT, logger
from deps import limiter

router = APIRouter(prefix="/v1/chess", tags=["Chess"])


@router.get("/state", summary="Get chess game state")
@limiter.limit("60/minute")
async def get_chess_state(request: Request) -> Dict[str, Any]:
    agent_base = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
    if not agent_base:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    url = f"{agent_base}/v1/chess/state"
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.get(url)
    except Exception as exc:
        logger.error(f"Chess state request failed: {exc}")
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Failed to reach chess state service") from exc
    if resp.status_code != 200:
        logger.error(f"Chess state service returned {resp.status_code}: {resp.text}")
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Chess state service returned an error")
    data = resp.json()
    if not isinstance(data, dict):
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Chess state service returned invalid data")
    return data
