"""Pydantic models and shared enums. Single source of truth for allowed languages."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


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
    text: str = Field(..., description="User message text")
    mode: str = Field("llm", description="Processing mode: 'llm' or 'agent'")
    agent_name: Optional[str] = Field(
        None, description="Agent name when mode='agent' (defaults to 'travel_planner')"
    )
