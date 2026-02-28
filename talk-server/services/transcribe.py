import os
import time

import httpx
from fastapi import HTTPException, UploadFile

from config import ASR_TIMEOUT, MAX_UPLOAD_BYTES, logger
from models import ALLOWED_LANGUAGES, TranscriptionResponse
from services.retry import retry_async


async def transcribe_audio(file: UploadFile, language: str) -> TranscriptionResponse:
    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Language must be one of {ALLOWED_LANGUAGES}")

    start_time = time.time()
    file_content = await file.read()
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")

    if language in ["english", "german"]:
        base = os.getenv("DWANI_API_BASE_URL_TRANSCRIPTION", "http://localhost:8000").rstrip("/")
        url = f"{base}/v1/audio/transcriptions"
        files = {"file": (file.filename, file_content, file.content_type), "model": (None, "Systran/faster-whisper-small")}

        async def _do():
            async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
                r = await client.post(url, files=files)
                if r.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Transcription failed: {r.text or r.status_code}")
                data = r.json()
                text = data.get("text", "")
                if not text:
                    raise HTTPException(status_code=500, detail="Transcription failed: empty result")
                return TranscriptionResponse(text=text)

        try:
            result = await retry_async(_do)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Transcription request failed: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
        logger.debug(f"Transcription completed in {time.time() - start_time:.2f}s")
        return result
    else:
        external_url = f"{os.getenv('DWANI_API_BASE_URL_ASR')}/transcribe/?language={language}"
        files = {"file": (file.filename, file_content, file.content_type)}

        async def _do():
            async with httpx.AsyncClient(timeout=ASR_TIMEOUT) as client:
                r = await client.post(external_url, files=files, headers={"accept": "application/json"})
                r.raise_for_status()
                return TranscriptionResponse(text=r.json().get("text", "") or "")

        try:
            result = await retry_async(_do)
        except httpx.TimeoutException:
            logger.error("Transcription service timed out")
            raise HTTPException(status_code=504, detail="Transcription service timeout")
        except httpx.HTTPStatusError as e:
            logger.error(f"Transcription HTTP error: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Transcription request failed: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
        logger.debug(f"Transcription completed in {time.time() - start_time:.2f}s")
        return result
