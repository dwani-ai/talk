"""Shared dependencies (e.g. rate limiter, auth)."""
import os
from typing import Optional

from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def require_api_key(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """Optional auth gate: enforced only when DWANI_API_KEY is configured."""
    configured_key = os.getenv("DWANI_API_KEY", "").strip()
    if not configured_key:
        return

    bearer_key = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_key = authorization[7:].strip()
    provided = x_api_key or bearer_key

    if not provided or provided != configured_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
