import base64
import os
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Query
from fastapi.responses import JSONResponse, Response

from config import TTS_TIMEOUT, logger
from deps import limiter
from models import ALLOWED_LANGUAGES, ChatRequest
from services import call_agent, call_llm, get_session_context, append_to_session, transcribe_audio

router = APIRouter(prefix="/v1", tags=["Chat"])


@router.post("/chat", summary="Text chat")
@limiter.limit("60/minute")
async def chat(request: Request, payload: ChatRequest) -> Dict[str, Any]:
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text must not be empty")

    session_id = (request.headers.get("X-Session-ID") or "").strip() or None
    context = get_session_context(session_id) if session_id else []

    if payload.mode == "agent":
        selected_agent = payload.agent_name or "travel_planner"
        agent_result = await call_agent(selected_agent, text, session_id=session_id)
        reply = agent_result["reply"]
        out: Dict[str, Any] = {"user": text, "reply": reply}
        if agent_result.get("warehouse_state") is not None:
            out["warehouse_state"] = agent_result["warehouse_state"]
        if agent_result.get("chess_state") is not None:
            out["chess_state"] = agent_result["chess_state"]
        if session_id:
            append_to_session(session_id, text, reply)
        return out
    else:
        reply = await call_llm(text, context=context)
        if session_id:
            append_to_session(session_id, text, reply)
        return {"user": text, "reply": reply}


@router.post(
    "/speech_to_speech",
    summary="Speech-to-Speech Conversion",
    description="Convert input speech to processed speech in the specified language.",
    tags=["Audio"],
    responses={
        200: {"description": "Audio stream", "content": {"audio/mp3": {"example": "Binary audio data"}}},
        400: {"description": "Invalid input or language"},
        413: {"description": "File too large"},
        429: {"description": "Rate limit exceeded"},
        504: {"description": "External API timeout"},
        500: {"description": "External API error"},
    },
)
@limiter.limit("20/minute")
async def speech_to_speech(
    request: Request,
    file: UploadFile = File(..., description="Audio file to process"),
    language: str = Query(..., description="Language of the audio (e.g. kannada, hindi, tamil, malayalam, telugu, marathi, english, german)"),
    mode: str = Query("llm", description="Processing mode: 'llm' or 'agent'"),
    agent_name: Optional[str] = Query(None, description="Agent name when mode='agent'"),
) -> Response:
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Language must be one of {ALLOWED_LANGUAGES}")

    logger.debug("Processing speech-to-speech request", extra={
        "endpoint": "/v1/speech_to_speech",
        "audio_filename": file.filename,
        "language": language,
        "client_ip": getattr(request.client, "host", None),
    })

    try:
        session_id = (request.headers.get("X-Session-ID") or "").strip() or None
        context = get_session_context(session_id) if session_id else []

        asr_text = await transcribe_audio(file=file, language=language)
        text = asr_text.text
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="No speech detected in the audio")

        if mode == "agent":
            selected_agent = agent_name or "travel_planner"
            agent_result = await call_agent(selected_agent, text, session_id=session_id)
            llm_text = agent_result["reply"]
        else:
            llm_text = await call_llm(text, context=context)

        if not llm_text or not llm_text.strip():
            raise HTTPException(status_code=502, detail="Text for TTS is empty")

        if session_id:
            append_to_session(session_id, text, llm_text)

        base_url = f"{os.getenv('DWANI_API_BASE_URL_TTS')}/v1/audio/speech"
        async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
            tts_response = await client.post(
                base_url,
                json={"text": llm_text},
                headers={"accept": "*/*", "Content-Type": "application/json"},
            )
            tts_response.raise_for_status()
            audio_bytes = tts_response.content

        if not audio_bytes or len(audio_bytes) == 0:
            logger.error("TTS returned empty audio", extra={"base_url": base_url, "status_code": tts_response.status_code})
            raise HTTPException(status_code=502, detail="TTS service returned empty audio; no MP3 data received")

        logger.info("TTS audio received", extra={"content_length": len(audio_bytes), "content_type": tts_response.headers.get("Content-Type")})

        return_json = request.query_params.get("format") == "json"
        if return_json:
            return JSONResponse(content={
                "transcription": text,
                "llm_response": llm_text,
                "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            })
        headers = {
            "Content-Disposition": "inline; filename=\"speech.mp3\"",
            "Cache-Control": "no-cache",
            "Content-Type": "audio/mp3",
        }
        return Response(content=audio_bytes, media_type="audio/mp3", headers=headers)
    except httpx.TimeoutException:
        logger.error("External speech-to-speech API timed out")
        raise HTTPException(status_code=504, detail="External API timeout")
    except httpx.HTTPError as e:
        logger.error(f"External speech-to-speech API error: {e}")
        raise HTTPException(status_code=502, detail=f"External API error: {str(e)}")
