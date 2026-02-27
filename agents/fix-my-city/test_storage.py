"""
Tests for fix-my-city SQLite storage. Run from repo root:
  pytest agents/fix-my-city/test_storage.py -v
Or from agents/fix-my-city:
  pytest test_storage.py -v
"""
import os
import sys
import tempfile

# Use a temp DB dir before importing storage so tests don't touch the real DB
_test_db_dir = tempfile.mkdtemp(prefix="fix_my_city_test_")
os.environ["FIX_MY_CITY_DB_DIR"] = _test_db_dir

_test_dir = os.path.dirname(os.path.abspath(__file__))
if _test_dir not in sys.path:
    sys.path.insert(0, _test_dir)

import storage  # noqa: E402


def _reset_storage():
    """Point storage at a fresh temp DB and reset connection."""
    storage._conn = None  # noqa: SLF001
    os.environ["FIX_MY_CITY_DB_DIR"] = tempfile.mkdtemp(prefix="fix_my_city_test_")
    storage.init_db()


def test_create_and_get_complaint():
    _reset_storage()
    data = {
        "city": "Bangalore",
        "area": "JP Nagar",
        "issue_type": "pothole",
        "description": "Large pothole near the park",
        "incident_date": "2025-02-27",
        "incident_time": "10:00",
        "session_id": "sess-123",
    }
    created = storage.create_complaint(data)
    assert "complaint_id" in created
    assert created["complaint_id"].startswith("C")
    assert created["city"] == "Bangalore"
    assert created["area"] == "JP Nagar"
    assert created["status"] == "open"

    got = storage.get_complaint_by_id(created["complaint_id"])
    assert got is not None
    assert got["complaint_id"] == created["complaint_id"]
    assert got["description"] == "Large pothole near the park"


def test_get_complaint_by_id_not_found():
    _reset_storage()
    assert storage.get_complaint_by_id("C99999") is None
    assert storage.get_complaint_by_id("nonexistent") is None


def test_find_complaints_by_filters():
    _reset_storage()
    data = {
        "city": "Mumbai",
        "area": "Bandra",
        "issue_type": "garbage",
        "description": "Uncleared garbage",
        "incident_date": "2025-02-26",
        "incident_time": "14:00",
        "session_id": "sess-456",
    }
    storage.create_complaint(data)
    storage.create_complaint({**data, "description": "Another pile"})

    results = storage.find_complaints({"city": "Mumbai", "area": "Bandra"}, limit=10)
    assert len(results) >= 2
    results = storage.find_complaints({"session_id": "sess-456"}, limit=10)
    assert len(results) >= 2

    results = storage.find_complaints({"city": "Delhi"}, limit=10)
    assert len(results) == 0


def test_update_complaint_status():
    _reset_storage()
    data = {
        "city": "Chennai",
        "area": "Anna Nagar",
        "issue_type": "streetlight",
        "description": "Streetlight not working",
        "incident_date": "2025-02-25",
        "incident_time": "19:00",
    }
    created = storage.create_complaint(data)
    cid = created["complaint_id"]

    updated = storage.update_complaint_status(cid, "in_progress", note="Team assigned")
    assert updated is not None
    assert updated["status"] == "in_progress"
    assert updated.get("note") == "Team assigned"

    updated2 = storage.update_complaint_status(cid, "resolved")
    assert updated2 is not None
    assert updated2["status"] == "resolved"

    assert storage.update_complaint_status("C99999", "resolved") is None


if __name__ == "__main__":
    test_create_and_get_complaint()
    print("test_create_and_get_complaint OK")
    test_get_complaint_by_id_not_found()
    print("test_get_complaint_by_id_not_found OK")
    test_find_complaints_by_filters()
    print("test_find_complaints_by_filters OK")
    test_update_complaint_status()
    print("test_update_complaint_status OK")
    print("All storage tests passed.")
