

import base64
import time
import os 

import argparse
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Form, Query
from pydantic import BaseModel, Field, ConfigDict

from fastapi.responses import RedirectResponse, StreamingResponse, Response
import requests
from typing import List, Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks

import logging
import logging.config
from logging.handlers import RotatingFileHandler

from openai import OpenAI
from openai import APIError as OpenAIAPIError
import tempfile
from pathlib import Path
import httpx

import uvicorn


logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "simple",
            "filename": "dwani_api.log",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "root": {
            "level": "INFO",
            "handlers": ["stdout", "file"],
        },
    },
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger("indic_all_server")


# FastAPI app setup with enhanced docs
app = FastAPI(
    title="dwani.ai API",
    description="A multimodal Inference API designed for Privacy",
    version="1.0.0",
    redirect_slashes=False,
    openapi_tags=[
        {"name": "Chat", "description": "Chat-related endpoints"},
        {"name": "Audio", "description": "Audio processing and TTS endpoints"},
        {"name": "Translation", "description": "Text translation endpoints"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ 
        "https://dwani.ai",
        "https://*.dwani.ai",
        "https://dwani-*.hf.space",
        "http://localhost:11080"
        ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TranscriptionResponse(BaseModel):
    text: str = Field(..., description="Transcribed text from the audio")

    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "Hello, how are you?"}}
    )

async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: str = Query(..., description="Language of the audio (kannada, hindi, tamil, english, german)")
):
    # Validate language
    allowed_languages = ["kannada", "hindi", "tamil", "english","german", "telugu" , "marathi" ]
    if language not in allowed_languages:
        raise HTTPException(status_code=400, detail=f"Language must be one of {allowed_languages}")
    
    start_time = time.time()
   
    if( language in ["english", "german"]):
        
        file_content = await file.read()
        files = {"file": (file.filename, file_content, file.content_type),
#                'model': (None, 'Systran/faster-whisper-large-v3')
                'model': (None, 'Systran/faster-whisper-small')
        }
        
        response = httpx.post('http://localhost:8000/v1/audio/transcriptions', files=files, timeout=30.0)

        if response.status_code == 200:
            transcription = response.json().get("text", "")
            if transcription:
                logger.debug(f"Transcription completed in {time.time() - start_time:.2f} seconds")
                return TranscriptionResponse(text=transcription)
            else:
                logger.debug("Transcription empty, try again.")
                raise HTTPException(status_code=500, detail="Transcription failed: empty result")
        else:
            logger.debug(f"Transcription error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {response.text or response.status_code}")
    else: 
        try:
            file_content = await file.read()
            files = {"file": (file.filename, file_content, file.content_type)}
            
            external_url = f"{os.getenv('DWANI_API_BASE_URL_ASR')}/transcribe/?language={language}"
            response = requests.post(
                external_url,
                files=files,
                headers={"accept": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            
            transcription = response.json().get("text", "")
            logger.debug(f"Transcription completed in {time.time() - start_time:.2f} seconds")
            return TranscriptionResponse(text=transcription or "")
        
        except requests.Timeout:
            logger.error("Transcription service timed out")
            raise HTTPException(status_code=504, detail="Transcription service timeout")
        except requests.RequestException as e:
            logger.error(f"Transcription request failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

# LLM (OpenAI-compatible, e.g. Gemma3)
LLM_MODEL = os.getenv("DWANI_LLM_MODEL", "gemma3")


def call_llm(user_text: str) -> str:
    """Send text to OpenAI-compatible LLM and return the assistant reply."""
    base_url = os.getenv("DWANI_API_BASE_URL_LLM", "").rstrip("/")
    if not base_url:
        raise ValueError("DWANI_API_BASE_URL_LLM is not set")
    # OpenAI client expects base_url to include /v1
    api_base = f"{base_url}/v1" if not base_url.endswith("/v1") else base_url
    try:
        client = OpenAI(base_url=api_base, api_key="dummy")
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You must respond in at most one line. Keep your reply to a single short sentence."},
                {"role": "user", "content": user_text},
            ],
            max_tokens=256,
        )
    except OpenAIAPIError as e:
        logger.error(f"LLM API error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")
    content = response.choices[0].message.content if response.choices else None
    if not content or not str(content).strip():
        raise HTTPException(
            status_code=502,
            detail="LLM returned empty response",
        )
    # Enforce single line for TTS (collapse newlines to space)
    return " ".join(str(content).strip().split())


from enum import Enum

class SupportedLanguage(str, Enum):
    kannada = "kannada"
    hindi = "hindi"
    tamil = "tamil"


@app.post("/v1/speech_to_speech",
          summary="Speech-to-Speech Conversion",
          description="Convert input speech to processed speech in the specified language by calling an external speech-to-speech API.",
          tags=["Audio"],
          responses={
              200: {"description": "Audio stream", "content": {"audio/mp3": {"example": "Binary audio data"}}},
              400: {"description": "Invalid input or language"},
              504: {"description": "External API timeout"},
              500: {"description": "External API error"}
          })
async def speech_to_speech(
    request: Request,
    file: UploadFile = File(..., description="Audio file to process"),
    language: str = Query(..., description="Language of the audio (kannada, hindi, tamil)")
) -> Response:
    # Validate language
    allowed_languages = [lang.value for lang in SupportedLanguage]
    if language not in allowed_languages:
        raise HTTPException(status_code=400, detail=f"Language must be one of {allowed_languages}")
    
    logger.debug("Processing speech-to-speech request", extra={
        "endpoint": "/v1/speech_to_speech",
        "audio_filename": file.filename,
        "language": language,
        "client_ip": getattr(request.client, "host", None)
    })

    try:
        asr_text = await transcribe_audio(file=file, language=language)
        text = asr_text.text
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="No speech detected in the audio")

        llm_text = call_llm(text)
        if not llm_text or not llm_text.strip():
            raise HTTPException(status_code=502, detail="LLM returned empty text for TTS")

        base_url = f"{os.getenv('DWANI_API_BASE_URL_TTS')}/v1/audio/speech"
        tts_response = requests.post(
            base_url,
            json={"text": llm_text},
            headers={"accept": "*/*", "Content-Type": "application/json"},
            timeout=30,
        )
        tts_response.raise_for_status()
        audio_bytes = tts_response.content

        if not audio_bytes or len(audio_bytes) == 0:
            logger.error(
                "TTS returned empty audio",
                extra={"base_url": base_url, "status_code": tts_response.status_code},
            )
            raise HTTPException(
                status_code=502,
                detail="TTS service returned empty audio; no MP3 data received",
            )

        logger.info(
            "TTS audio received",
            extra={"content_length": len(audio_bytes), "content_type": tts_response.headers.get("Content-Type")},
        )

        return_json = request.query_params.get("format") == "json"
        if return_json:
            from fastapi.responses import JSONResponse
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
    except requests.Timeout:
        logger.error("External speech-to-speech API timed out")
        raise HTTPException(status_code=504, detail="External API timeout")
    except requests.RequestException as e:
        logger.error(f"External speech-to-speech API error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"External API error: {str(e)}")
    


if __name__ == "__main__":
    
    external_api_base_url_llm = os.getenv("DWANI_API_BASE_URL_LLM")
    if not external_api_base_url_llm:
        raise ValueError("Environment variable DWANI_API_BASE_URL_LLM must be set")
    
    
    external_api_base_url_tts = os.getenv("DWANI_API_BASE_URL_TTS")
    if not external_api_base_url_tts:
        raise ValueError("Environment variable DWANI_API_BASE_URL_TTS must be set")
    
    external_api_base_url_asr = os.getenv("DWANI_API_BASE_URL_ASR")
    if not external_api_base_url_asr:
        raise ValueError("Environment variable DWANI_API_BASE_URL_ASR must be set")
    
    
    parser = argparse.ArgumentParser(description="Run the FastAPI server.")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the server on.")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)