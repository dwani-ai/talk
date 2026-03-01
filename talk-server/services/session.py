import hashlib
import json
import os
from typing import Dict, List, Optional

from config import SESSION_CONTEXT_LIMIT, SESSION_MAX_HISTORY
from config import logger

try:
    import redis
except Exception:  # pragma: no cover - optional dependency at runtime
    redis = None

_session_store: Dict[str, List[Dict[str, str]]] = {}
_session_order: List[str] = []
_MAX_SESSIONS = 5000
_REDIS_TTL_SECONDS = int(os.getenv("DWANI_SESSION_TTL_SECONDS", "86400"))
_REDIS_CLIENT: Optional["redis.Redis"] = None


def _redis_client() -> Optional["redis.Redis"]:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    if redis is None:
        return None
    url = os.getenv("DWANI_REDIS_URL", "").strip()
    if not url:
        return None
    try:
        _REDIS_CLIENT = redis.Redis.from_url(url, decode_responses=True)
        return _REDIS_CLIENT
    except Exception as exc:
        logger.warning("Failed to initialize Redis session client: %s", exc)
        return None


def _session_key(session_id: str) -> str:
    # Avoid raw session IDs in Redis keys/logs.
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return f"dwani:session:{digest}"


def _load_redis_history(session_id: str) -> Optional[List[Dict[str, str]]]:
    client = _redis_client()
    if client is None:
        return None
    try:
        payload = client.get(_session_key(session_id))
        if not payload:
            return []
        parsed = json.loads(payload)
        if isinstance(parsed, list):
            return parsed
    except Exception as exc:
        logger.warning("Redis session read failed; falling back to memory: %s", exc)
    return None


def _save_redis_history(session_id: str, history: List[Dict[str, str]]) -> bool:
    client = _redis_client()
    if client is None:
        return False
    try:
        client.setex(_session_key(session_id), _REDIS_TTL_SECONDS, json.dumps(history))
        return True
    except Exception as exc:
        logger.warning("Redis session write failed; falling back to memory: %s", exc)
        return False


def get_session_context(session_id: str) -> List[Dict[str, str]]:
    if not session_id:
        return []
    redis_history = _load_redis_history(session_id)
    if redis_history is not None:
        return redis_history[-SESSION_CONTEXT_LIMIT:]
    history = _session_store.get(session_id, [])
    return history[-SESSION_CONTEXT_LIMIT:]


def append_to_session(session_id: str, user: str, assistant: str) -> None:
    if not session_id:
        return
    redis_history = _load_redis_history(session_id)
    if redis_history is not None:
        redis_history.append({"role": "user", "content": user})
        redis_history.append({"role": "assistant", "content": assistant})
        if len(redis_history) > SESSION_MAX_HISTORY:
            redis_history = redis_history[-SESSION_MAX_HISTORY:]
        if _save_redis_history(session_id, redis_history):
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
