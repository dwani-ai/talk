"""Environment-derived configuration. Do not depend on other app modules."""
import os
import logging.config


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return int(v) if v else default


ASR_TIMEOUT = _env_int("DWANI_ASR_TIMEOUT", 30)
TTS_TIMEOUT = _env_int("DWANI_TTS_TIMEOUT", 30)
LLM_TIMEOUT = _env_int("DWANI_LLM_TIMEOUT", 60)
MAX_UPLOAD_BYTES = _env_int("DWANI_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)  # 25MB
MAX_RETRIES = _env_int("DWANI_MAX_RETRIES", 2)

SESSION_CONTEXT_LIMIT = _env_int("DWANI_SESSION_CONTEXT_LIMIT", 10)
SESSION_MAX_HISTORY = _env_int("DWANI_SESSION_MAX_HISTORY", 20)
_MAX_SESSIONS = 5000

LLM_MODEL = os.getenv("DWANI_LLM_MODEL", "gemma3")
AGENT_BASE_URL = os.getenv("DWANI_AGENT_BASE_URL", "").rstrip("/")
LOG_FORMAT = os.getenv("DWANI_LOG_FORMAT", "json").strip().lower()


_FORMATTERS = {
    "plain": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
}
if LOG_FORMAT == "json":
    _FORMATTERS["json"] = {
        "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
        "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s %(session_id)s",
    }

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": _FORMATTERS,
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "plain",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "root": {
            "level": "INFO",
            "handlers": ["stdout"],
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("indic_all_server")
