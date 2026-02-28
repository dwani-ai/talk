from typing import Dict, List

from config import SESSION_CONTEXT_LIMIT, SESSION_MAX_HISTORY

_session_store: Dict[str, List[Dict[str, str]]] = {}
_session_order: List[str] = []
_MAX_SESSIONS = 5000


def get_session_context(session_id: str) -> List[Dict[str, str]]:
    if not session_id:
        return []
    history = _session_store.get(session_id, [])
    return history[-SESSION_CONTEXT_LIMIT:]


def append_to_session(session_id: str, user: str, assistant: str) -> None:
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
