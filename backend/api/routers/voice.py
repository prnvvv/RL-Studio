"""Voice transcription API.

The browser uploads a WAV recording here (mono 16-bit PCM, 16 or 24 kHz); the backend forwards it to Meta's hosted
Muse Voice Transcribe model. MODAL_API_KEY never reaches the client, and audio is processed in memory only (never
written to disk or the database).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.ai.errors import AIError, AIPayloadTooLargeError
from backend.ai.service import AIService, get_ai_service

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])

RATE_LIMIT = 10  # requests
RATE_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > RATE_WINDOW_SECONDS:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        return False


def _error(exc: AIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}},
    )


@router.get("/status")
def voice_status(service: Annotated[AIService, Depends(get_ai_service)]) -> dict[str, Any]:
    """Whether voice input is available (no credentials are returned)."""
    return service.status()["tasks"]["voice_transcription"]


@router.post("/transcribe")
async def transcribe(
    request: Request,
    audio: Annotated[UploadFile, File()],
    service: Annotated[AIService, Depends(get_ai_service)],
    language: Annotated[str | None, Form()] = None,
) -> Any:
    client = request.client.host if request.client else "unknown"
    if _rate_limited(client):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "AI-003", "message": "too many transcription requests", "retryable": True}},
        )
    limit = service.settings.max_audio_bytes
    # read at most limit + 1 bytes so an oversized upload is never fully buffered
    content = await audio.read(limit + 1)
    await audio.close()
    try:
        if len(content) > limit:
            raise AIPayloadTooLargeError(f"the audio file exceeds the {limit // (1024 * 1024)} MB limit")
        result = await run_in_threadpool(
            service.transcribe, audio.filename or "recording", content, audio.content_type, language
        )
    except AIError as exc:
        return _error(exc)
    finally:
        del content  # audio is never persisted
    return {
        "text": result["text"],
        "language": result["language"],
        "duration_seconds": result["duration"],
        "turns": result["turns"],
        "model": result["model"],
        "provider": result["provider"],
        "request_id": result["request_id"],
    }
