import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException
from openai import AsyncOpenAI
from openai import APIError as OpenAIAPIError

from config import AGENT_BASE_URL, LLM_MODEL, LLM_TIMEOUT, logger
from services.retry import retry_async


async def call_llm(
    user_text: str,
    context: Optional[List[Dict[str, str]]] = None,
    request_id: Optional[str] = None,
) -> str:
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
        llm_api_key = os.getenv("DWANI_LLM_API_KEY", "dummy")
        client = AsyncOpenAI(base_url=api_base, api_key=llm_api_key, timeout=httpx.Timeout(LLM_TIMEOUT))
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=256,
            extra_headers={"X-Request-ID": request_id} if request_id else None,
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


async def call_agent(
    agent_name: str,
    user_text: str,
    session_id: Optional[str],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Send text to agents service. Returns reply and optional state payloads."""
    if not AGENT_BASE_URL:
        raise HTTPException(status_code=502, detail="Agent service base URL is not configured")
    if not session_id:
        raise HTTPException(status_code=400, detail="Agent mode requires a session_id")

    url = f"{AGENT_BASE_URL}/v1/agents/{agent_name}/chat"
    payload = {"session_id": session_id, "message": user_text}
    agents_api_key = os.getenv("AGENTS_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if agents_api_key:
        headers["X-API-Key"] = agents_api_key
    if request_id:
        headers["X-Request-ID"] = request_id

    async def _do():
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            return await client.post(url, json=payload, headers=headers)

    try:
        resp = await retry_async(_do)
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
    result: Dict[str, Any] = {"reply": " ".join(str(reply).strip().split())}
    if data.get("warehouse_state") is not None and isinstance(data["warehouse_state"], dict):
        result["warehouse_state"] = data["warehouse_state"]
    if data.get("chess_state") is not None and isinstance(data["chess_state"], dict):
        result["chess_state"] = data["chess_state"]
    return result
