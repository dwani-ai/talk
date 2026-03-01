"""Tests for /v1/speech_to_speech endpoint."""
import io

import pytest
from fastapi.testclient import TestClient

import main
from routers import chat as chat_router


@pytest.fixture
def client():
    return TestClient(main.app)


def test_speech_to_speech_rejects_invalid_language(client: TestClient):
    """Invalid language returns 400."""
    res = client.post(
        "/v1/speech_to_speech",
        params={"language": "invalid_lang", "mode": "llm"},
        files={"file": ("audio.wav", io.BytesIO(b"fake"), "audio/wav")},
    )
    assert res.status_code == 400
    assert "language" in res.json().get("detail", "").lower()


def test_speech_to_speech_rejects_file_too_large(client: TestClient, monkeypatch):
    """File over MAX_UPLOAD_BYTES returns 413."""
    from config import MAX_UPLOAD_BYTES

    big = io.BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1))
    res = client.post(
        "/v1/speech_to_speech",
        params={"language": "kannada", "mode": "llm"},
        files={"file": ("big.wav", big, "audio/wav")},
    )
    assert res.status_code == 413


def test_speech_to_speech_returns_json_when_mocked(client: TestClient, monkeypatch):
    """With transcribe, LLM and TTS mocked, returns 200 and JSON with transcription, llm_response, audio_base64."""
    from models import TranscriptionResponse

    async def fake_transcribe(file, language, request_id=None):
        return TranscriptionResponse(text="hello")

    async def fake_call_llm(user_text, context=None, request_id=None):
        return "hi there"

    class FakeTtsResponse:
        status_code = 200
        content = b"fake_mp3_bytes"
        headers = {}

        def raise_for_status(self):
            pass

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return FakeTtsResponse()

    monkeypatch.setattr(chat_router, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(chat_router, "call_llm", fake_call_llm)
    monkeypatch.setattr("routers.chat.httpx.AsyncClient", FakeHttpClient)

    res = client.post(
        "/v1/speech_to_speech",
        params={"language": "kannada", "mode": "llm", "format": "json"},
        files={"file": ("a.wav", io.BytesIO(b"audio"), "audio/wav")},
        headers={"X-Session-ID": "test-session"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("transcription") == "hello"
    assert data.get("llm_response") == "hi there"
    assert "audio_base64" in data
