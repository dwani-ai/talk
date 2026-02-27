import os
import sys
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# Ensure fix-my-city dir is on path so "storage" resolves to fix-my-city/storage.py
_FIX_MY_CITY_DIR = os.path.dirname(os.path.abspath(__file__))
if _FIX_MY_CITY_DIR not in sys.path:
    sys.path.insert(0, _FIX_MY_CITY_DIR)

from storage import (
    create_complaint as storage_create_complaint,
    find_complaints,
    get_complaint_by_id,
    update_complaint_status as storage_update_complaint_status,
)


load_dotenv()


logger = logging.getLogger("fix_my_city_agent")


MODEL = LiteLlm(
    model=os.getenv("LITELLM_MODEL_NAME"),
    api_base=os.getenv("LITELLM_API_BASE"),
    api_key=os.getenv("LITELLM_API_KEY"),
)


FIX_MY_CITY_INSTRUCTION = """
You are a helpful city complaint assistant. You help citizens register civic complaints (e.g. potholes, garbage, streetlights, water, noise) and check the status of their previous complaints.

- Users may speak or type in Kannada, Hindi, Tamil, Malayalam, Telugu, Marathi, English, or German.
- Detect the user's language from their message and always answer in the SAME language.
- Keep responses short and TTS-friendly (one or two short sentences when possible).

When registering a new complaint you MUST collect:
1) City
2) Area / locality / neighborhood
3) Date of the incident (e.g. today, yesterday, or a specific date)
4) Time of the incident (e.g. morning, 10 AM, afternoon)
5) Type of issue (e.g. pothole, garbage, streetlight, water, noise, or other)
6) A short description of the problem

Do not call create_complaint until you have all of: city, area, incident_date, incident_time, issue_type, and description. If any is missing, ask for it in one brief question.

After creating a complaint, tell the user their complaint ID clearly and that they can check status later by saying the complaint ID or describing the complaint.

When the user wants to check status:
- If they give a complaint ID (number or code), use get_complaint_status with that complaint_id.
- If they do not know the ID, use get_complaint_status with city, area, and optionally incident_date or issue_type to find their complaint. If multiple complaints match, list them briefly and ask which one they mean.

Be concise and practical. Confirm key details before submitting.
"""


def _session_id_from_context(tool_context: ToolContext) -> str:
    """Get session id from runner context if available."""
    return getattr(tool_context, "session_id", None) or getattr(
        getattr(tool_context, "session", None), "id", None
    ) or ""


def create_complaint(
    tool_context: ToolContext,
    city: str,
    area: str,
    issue_type: str,
    description: str,
    incident_date: str,
    incident_time: str,
    user_contact: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a new city complaint. Call this only when you have all required fields: city, area, issue_type, description, incident_date, incident_time."""
    session_id = _session_id_from_context(tool_context)
    data = {
        "city": (city or "").strip(),
        "area": (area or "").strip(),
        "issue_type": (issue_type or "other").strip().lower(),
        "description": (description or "").strip(),
        "incident_date": (incident_date or "").strip(),
        "incident_time": (incident_time or "").strip(),
        "user_contact": (user_contact or "").strip() or None,
        "session_id": session_id,
    }
    if not data["city"] or not data["area"] or not data["description"]:
        return {"error": "city, area, and description are required"}
    if not data["incident_date"] or not data["incident_time"]:
        return {"error": "incident_date and incident_time are required"}
    created = storage_create_complaint(data)
    return {
        "complaint_id": created["complaint_id"],
        "status": created.get("status", "open"),
        "summary": f"Complaint {created['complaint_id']} registered for {data['city']}, {data['area']} ({data['issue_type']}).",
    }


def get_complaint_status(
    tool_context: ToolContext,
    complaint_id: Optional[str] = None,
    city: Optional[str] = None,
    area: Optional[str] = None,
    incident_date: Optional[str] = None,
    issue_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Get status of a complaint. Either pass complaint_id (e.g. C123) for exact lookup, or pass city, area, and optionally incident_date/issue_type to search. Returns the most recent matching complaint if multiple match."""
    if complaint_id:
        c = get_complaint_by_id(str(complaint_id).strip())
        if not c:
            return {"found": False, "message": "No complaint found with that ID."}
        return {
            "found": True,
            "complaint_id": c["complaint_id"],
            "status": c.get("status", "open"),
            "city": c.get("city"),
            "area": c.get("area"),
            "issue_type": c.get("issue_type"),
            "description": c.get("description"),
            "incident_date": c.get("incident_date"),
            "incident_time": c.get("incident_time"),
            "updated_at": c.get("updated_at"),
        }
    filters: Dict[str, Any] = {}
    session_id = _session_id_from_context(tool_context)
    if session_id:
        filters["session_id"] = session_id
    if city:
        filters["city"] = (city or "").strip()
    if area:
        filters["area"] = (area or "").strip()
    if incident_date:
        filters["incident_date"] = (incident_date or "").strip()
    if issue_type:
        filters["issue_type"] = (issue_type or "").strip().lower()
    if not filters:
        return {"found": False, "message": "Provide complaint_id or at least city and area to search."}
    results: List[Dict[str, Any]] = find_complaints(filters, limit=5)
    if not results:
        return {"found": False, "message": "No matching complaints found."}
    c = results[0]
    return {
        "found": True,
        "complaint_id": c["complaint_id"],
        "status": c.get("status", "open"),
        "city": c.get("city"),
        "area": c.get("area"),
        "issue_type": c.get("issue_type"),
        "description": c.get("description"),
        "incident_date": c.get("incident_date"),
        "incident_time": c.get("incident_time"),
        "updated_at": c.get("updated_at"),
        "multiple_match": len(results) > 1,
    }


def update_complaint_status(
    tool_context: ToolContext,
    complaint_id: str,
    status: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Update the status of a complaint (e.g. to resolved or in_progress). Allowed status values: open, in_progress, resolved, closed."""
    allowed = {"open", "in_progress", "resolved", "closed"}
    if (status or "").strip().lower() not in allowed:
        return {"error": f"status must be one of: {', '.join(sorted(allowed))}"}
    updated = storage_update_complaint_status(
        str(complaint_id).strip(), (status or "").strip().lower(), (note or "").strip() or None
    )
    if not updated:
        return {"error": "Complaint not found."}
    return {
        "complaint_id": updated["complaint_id"],
        "status": updated.get("status"),
        "message": "Status updated.",
    }


root_fix_my_city_agent = Agent(
    name="fix_my_city",
    model=MODEL,
    description="Helps register city complaints and check their status.",
    instruction=FIX_MY_CITY_INSTRUCTION,
    tools=[create_complaint, get_complaint_status, update_complaint_status],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.3,
    ),
)
