import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, Request

from config import LLM_TIMEOUT, logger
from deps import get_optional_user, limiter
from models import WarehouseCommandRequest

router = APIRouter(prefix="/v1/warehouse", tags=["Warehouse"])


@router.get("/state", summary="Get warehouse robots and items state")
@limiter.limit("60/minute")
async def get_warehouse_state(request: Request, __=Depends(get_optional_user)) -> Dict[str, Any]:
    agent_base = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
    if not agent_base:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    url = f"{agent_base}/v1/warehouse/state"
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.get(url)
    except Exception as exc:
        logger.error(f"Warehouse state request failed: {exc}")
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Failed to reach warehouse state service") from exc
    if resp.status_code != 200:
        logger.error(f"Warehouse state service returned {resp.status_code}: {resp.text}")
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Warehouse state service returned an error")
    data = resp.json()
    if not isinstance(data, dict):
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Warehouse state service returned invalid data")
    return data


@router.post("/command", summary="Send a deterministic warehouse command")
@limiter.limit("60/minute")
async def proxy_warehouse_command(request: Request, body: WarehouseCommandRequest, __=Depends(get_optional_user)) -> Dict[str, Any]:
    agent_base = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
    if not agent_base:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    url = f"{agent_base}/v1/warehouse/command"
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(url, json=body.model_dump())
    except Exception as exc:
        logger.error(f"Warehouse command request failed: {exc}")
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Failed to reach warehouse command service") from exc
    if resp.status_code != 200:
        logger.error(f"Warehouse command service returned {resp.status_code}: {resp.text}")
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Warehouse command service returned an error")
    data = resp.json()
    if not isinstance(data, dict):
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Warehouse command service returned invalid data")
    return data
