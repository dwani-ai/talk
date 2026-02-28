"""Pydantic models and shared enums. Single source of truth for allowed languages."""
from enum import Enum
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


class SupportedLanguage(str, Enum):
    """Single source of truth for allowed languages (UI, ASR, speech_to_speech)."""
    kannada = "kannada"
    hindi = "hindi"
    tamil = "tamil"
    malayalam = "malayalam"
    telugu = "telugu"
    marathi = "marathi"
    english = "english"
    german = "german"


ALLOWED_LANGUAGES = [lang.value for lang in SupportedLanguage]
ALLOWED_AGENTS = [
    "travel_planner",
    "viva_examiner",
    "fix_my_city",
    "orchestrator",
    "warehouse_orchestrator",
    "chess_orchestrator",
]
DEFAULT_AGENT_NAME = "travel_planner"


class TranscriptionResponse(BaseModel):
    text: str = Field(..., description="Transcribed text from the audio")
    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "Hello, how are you?"}}
    )


class WarehouseCommandRequest(BaseModel):
    robot: str = Field(..., description="Robot to control: 'uav', 'ugv', or 'arm'.")
    action: Optional[str] = Field(default=None, description="Action: move, pick, drop, pick_from_stack, place_on_stack.")
    direction: Optional[str] = Field(default=None, description="Direction: north, south, east, or west.")
    item_id: Optional[str] = Field(default=None)
    stack_id: Optional[str] = Field(default=None)
    x: Optional[float] = Field(default=None)
    y: Optional[float] = Field(default=None)
    z: Optional[float] = Field(default=None)


class ChatRequest(BaseModel):
    text: str = Field(..., description="User message text", min_length=1, max_length=4000)
    mode: Literal["llm", "agent"] = Field("llm", description="Processing mode: 'llm' or 'agent'")
    agent_name: Optional[str] = Field(
        None,
        description="Agent name when mode='agent' (defaults to 'travel_planner')",
        min_length=1,
        max_length=64,
    )

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if value not in ALLOWED_AGENTS:
            raise ValueError(f"agent_name must be one of {ALLOWED_AGENTS}")
        return value
