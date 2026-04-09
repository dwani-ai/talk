import os
import base64
import json
import time
from typing import Optional

import httpx
from fastapi import HTTPException, UploadFile

from config import ASR_TIMEOUT, MAX_UPLOAD_BYTES, logger
from models import TranscriptionResponse
from services.retry import retry_async


_TRANSCRIBE_TASK_PROMPT = (
    "Transcribe the audio verbatim in its native script. "
    "Output only the transcribed text. "
    "Do not translate, explain, answer questions, or add labels or commentary."
)


def _transcription_only_text(raw: str) -> str:
    s = raw.strip()
    low = s.lower()
    key = "response:"
    if key in low:
        s = s[: low.index(key)].strip()
    for line in s.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("transcription:"):
            return stripped.split(":", 1)[1].strip()
    out_lines = []
    for line in s.splitlines():
        if line.strip().lower().startswith("language:"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines).strip() or raw.strip()


async def transcribe_audio(file: UploadFile, request_id: Optional[str] = None) -> TranscriptionResponse:
    start_time = time.time()
    file_content = await file.read()
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")

    if not file_content:
        raise HTTPException(status_code=400, detail="Empty audio file")

    mime = file.content_type or "audio/wav"
    b64 = base64.standard_b64encode(file_content).decode("ascii")
    audio_data_url = f"data:{mime};base64,{b64}"

    chat_url = os.getenv("DWANI_CHAT_COMPLETIONS_URL", "http://localhost:8000/v1/chat/completions")
    payload = {
        "model": "gemma4",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "audio_url", "audio_url": {"url": audio_data_url}},
                    {"type": "text", "text": _TRANSCRIBE_TASK_PROMPT},
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 512,
    }

    async def _do():
        try:
            async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
                headers = {"Content-Type": "application/json"}
                if request_id:
                    headers["X-Request-ID"] = request_id
                return await client.post(chat_url, headers=headers, json=payload)
        except httpx.TimeoutException:
            logger.error("Chat completions transcription timed out")
            raise HTTPException(status_code=504, detail="Transcription service timeout")
        except httpx.RequestError as e:
            logger.error(f"Chat completions request failed: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    try:
        response = await retry_async(_do)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

    if response.status_code != 200:
        logger.debug(f"Transcription error: {response.status_code} - {response.text}")
        raise HTTPException(
            status_code=502,
            detail=f"Chat completions error: {response.status_code} {response.text}",
        )

    try:
        body = response.json()
        choices = body.get("choices") or []
        text = ""
        if choices:
            msg = choices[0].get("message") or {}
            text = (msg.get("content") or "").strip()
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.error(f"Invalid chat completions response: {e}")
        raise HTTPException(status_code=502, detail="Invalid response from transcription service")

    if not text:
        logger.debug("Transcription empty from chat completions")
        raise HTTPException(status_code=500, detail="Transcription failed: empty response")

    text = _transcription_only_text(text)
    if not text:
        raise HTTPException(status_code=500, detail="Transcription failed: empty response")

    logger.debug(f"Transcription completed in {time.time() - start_time:.2f}s")
    return TranscriptionResponse(text=text)
