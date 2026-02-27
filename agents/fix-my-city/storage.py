"""
SQLite-backed storage for fix-my-city complaints.
DB file is created under a data directory (env FIX_MY_CITY_DB_DIR or default ./data).
"""
import os
import sqlite3
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fix_my_city_storage")

_DB_DIR_ENV = "FIX_MY_CITY_DB_DIR"
_DEFAULT_DIR = "data"
_DB_FILENAME = "fix_my_city.db"

_conn: Optional[sqlite3.Connection] = None


def _db_path() -> str:
    base = os.getenv(_DB_DIR_ENV)
    if not base:
        # Default: data/ next to this file (fix-my-city/storage.py -> fix-my-city/data/)
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), _DEFAULT_DIR)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, _DB_FILENAME)


def _get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = _db_path()
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_db(_conn)
    return _conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id TEXT NOT NULL UNIQUE,
            session_id TEXT,
            user_contact TEXT,
            city TEXT NOT NULL,
            area TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            description TEXT NOT NULL,
            incident_date TEXT NOT NULL,
            incident_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_complaints_session ON complaints(session_id);
        CREATE INDEX IF NOT EXISTS idx_complaints_city_area ON complaints(city, area);
        CREATE INDEX IF NOT EXISTS idx_complaints_incident_date ON complaints(incident_date);
    """)
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row) if row else {}


def create_complaint(data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a complaint and return the created record with complaint_id."""
    conn = _get_connection()
    now = _now_iso()
    placeholder = f"_tmp_{uuid.uuid4().hex[:12]}"
    cursor = conn.execute(
        """
        INSERT INTO complaints (
            complaint_id, session_id, user_contact, city, area, issue_type,
            description, incident_date, incident_time, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """,
        (
            placeholder,
            data.get("session_id") or "",
            data.get("user_contact") or "",
            data["city"],
            data["area"],
            data["issue_type"],
            data["description"],
            data["incident_date"],
            data["incident_time"],
            now,
            now,
        ),
    )
    row_id = cursor.lastrowid
    complaint_id = f"C{row_id}"
    conn.execute("UPDATE complaints SET complaint_id = ? WHERE id = ?", (complaint_id, row_id))
    conn.commit()
    out = get_complaint_by_id(complaint_id)
    assert out is not None
    return out


def get_complaint_by_id(complaint_id: str) -> Optional[Dict[str, Any]]:
    """Return one complaint by complaint_id (e.g. C123) or None."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM complaints WHERE complaint_id = ?",
        (str(complaint_id).strip(),),
    ).fetchone()
    return _row_to_dict(row) if row else None


def find_complaints(
    filters: Dict[str, Any],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Find complaints by optional session_id, city, area, incident_date, issue_type. Most recent first."""
    conn = _get_connection()
    conditions = []
    args: List[Any] = []
    if filters.get("session_id"):
        conditions.append("session_id = ?")
        args.append(filters["session_id"])
    if filters.get("city"):
        conditions.append("city = ?")
        args.append(filters["city"])
    if filters.get("area"):
        conditions.append("area = ?")
        args.append(filters["area"])
    if filters.get("incident_date"):
        conditions.append("incident_date = ?")
        args.append(filters["incident_date"])
    if filters.get("issue_type"):
        conditions.append("issue_type = ?")
        args.append(filters["issue_type"])
    where = " AND ".join(conditions) if conditions else "1=1"
    args.append(limit)
    rows = conn.execute(
        f"SELECT * FROM complaints WHERE {where} ORDER BY created_at DESC LIMIT ?",
        args,
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_complaint_status(
    complaint_id: str,
    status: str,
    note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update status (and optional note) for a complaint. Returns updated row or None."""
    conn = _get_connection()
    now = _now_iso()
    conn.execute(
        "UPDATE complaints SET status = ?, note = ?, updated_at = ? WHERE complaint_id = ?",
        (status, note or "", now, str(complaint_id).strip()),
    )
    conn.commit()
    return get_complaint_by_id(complaint_id)


def init_db() -> None:
    """Explicitly ensure DB and table exist (e.g. for tests or startup)."""
    _get_connection()
