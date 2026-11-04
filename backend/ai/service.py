"""Task-routed hosted AI service (Meta Model API only).

Only the model registered for a task is invoked. A fallback is used only when it is registered, enabled and
modality-compatible (Muse Wonder preview tasks -> Muse Spark), and the model actually used is always reported.
Output is advisory: nothing here decides a verification verdict.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import threading
import time
import wave
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .clients import MetaClient
from .errors import (
    AIAuthError,
    AIConfigurationError,
    AIError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIPayloadTooLargeError,
    AIProviderUnavailableError,
    AIQuotaError,
    AIRateLimitError,
    AITimeoutError,
    AIUnsupportedTaskError,
)
from .imaging import inspect_image
from .registry import Modality, Task, TaskSpec, build_registry
from .settings import AISettings

logger = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)

#: errors after which trying the (compatible) fallback model is reasonable
_FALLBACK_ON = (AIRateLimitError, AITimeoutError, AIProviderUnavailableError, AIModelUnavailableError)

#: Meta Voice Transcribe accepts mono 16-bit PCM WAV at 16 or 24 kHz, up to 10 minutes / 32 MB
VOICE_SAMPLE_RATES = (16000, 24000)
VOICE_MAX_SECONDS = 600
VOICE_MAX_BYTES = 32 * 1024 * 1024
_LANGUAGE_NAMES = {"en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian",
                   "pt": "Portuguese", "hi": "Hindi", "ja": "Japanese", "zh": "Chinese", "ko": "Korean"}
SEGMENT_CACHE_SIZE = 32
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


def validate_audio(content: bytes, content_type: str | None, max_bytes: int) -> str:
    """Validate a WAV recording against Meta's documented constraints; returns ``audio/wav``.

    Meta transcribes only mono, 16-bit PCM WAV at 16 kHz or 24 kHz (<= 10 minutes, <= 32 MB). The browser client
    encodes to that format; anything else is rejected with an actionable message rather than silently converted.
    """
    if not content:
        raise AIInvalidInputError("the audio recording is empty")
    if len(content) > min(max_bytes, VOICE_MAX_BYTES):
        raise AIPayloadTooLargeError(f"the audio file exceeds the {min(max_bytes, VOICE_MAX_BYTES) // (1024 * 1024)} MB limit")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in {"audio/wav", "audio/x-wav", "audio/wave"}:
        raise AIInvalidInputError("unsupported audio type: Meta transcription requires a WAV recording")
    if content[:4] != b"RIFF" or content[8:12] != b"WAVE":
        raise AIInvalidInputError("the audio content does not match its declared type")
    try:
        with wave.open(io.BytesIO(content), "rb") as wav:
            channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
    except (wave.Error, EOFError) as exc:
        raise AIInvalidInputError("the WAV file is not readable PCM audio") from exc
    if channels != 1 or width != 2 or rate not in VOICE_SAMPLE_RATES:
        raise AIInvalidInputError("audio must be mono 16-bit PCM WAV at 16 kHz or 24 kHz")
    if frames == 0:
        raise AIInvalidInputError("the audio recording is empty")
    if frames / rate > VOICE_MAX_SECONDS:
        raise AIPayloadTooLargeError("the recording is longer than the 10 minute limit")
    return "audio/wav"


def validate_image(content: bytes, content_type: str | None, max_bytes: int) -> str:
    """Validate size, real format and dimensions; returns the verified MIME type."""
    return inspect_image(content, max_bytes, declared_type=content_type).mime


def extract_json(text: str) -> Any:
    """Parse a model's JSON reply, tolerating a markdown fence or a short preamble. Raises ``ValueError``."""
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(body[start : end + 1])


@dataclass(frozen=True)
class AIResult:
    task: str
    provider: str
    model: str
    fallback_used: bool
    request_id: str | None
    usage: dict[str, Any] | None
    text: str = ""
    parsed: BaseModel | None = None


class AIService:
    def __init__(self, settings: AISettings, *, client: MetaClient | None = None) -> None:
        self.settings = settings
        self.registry = build_registry(settings)
        self.client = client or MetaClient(
            settings.base_url, settings.api_key, timeout=settings.timeout_seconds, backoff=settings.retry_backoff_seconds)
        #: model id -> verification state from the last ``verify_models`` call (never inferred from configuration)
        self._access: dict[str, dict[str, str]] = {}
        self._last_check: float | None = None
        self._segments: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    # -- status -----------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """Per-task availability. Never contains credentials. 'configured' does not mean 'verified'."""
        has_key = self.client.configured
        tasks = {}
        for t, s in self.registry.items():
            if not s.enabled:
                state, reason = "disabled", s.disabled_reason
            elif not has_key:
                state, reason = "unconfigured", "MODEL_API_KEY is not configured"
            else:
                state, reason = "configured", ""
            access = self._access.get(s.model, {"state": "not_verified", "detail": "run the connectivity check"})
            tasks[t.value] = {
                "provider": s.provider.value, "model": s.model or None, "modality": s.modality.value,
                "state": state, "reason": reason or None, "preview": s.preview,
                "fallback": s.fallback.value if s.fallback else None,
                "model_access": access["state"], "model_access_detail": access["detail"],
            }
        return {"config": self.settings.public(), "tasks": tasks,
                "last_connectivity_test": self._last_check}

    def verify_models(self) -> dict[str, dict[str, str]]:
        """Check the configured model ids against the key's live catalogue (``GET /models``).

        Listing a model is evidence of access, not of a working inference call. Failures are recorded by category.
        """
        models = {s.model for s in self.registry.values() if s.model and s.enabled}
        try:
            available = self.client.list_models()
        except AIError as exc:
            state = _error_state(exc)
            result = {m: {"state": state, "detail": f"{exc.code}: {exc.message}"} for m in models}
        else:
            result = {m: ({"state": "listed", "detail": "the model is enabled for this key"} if m in available
                          else {"state": "not_listed", "detail": "the model is not in this key's catalogue"})
                      for m in models}
        self._access.update(result)
        self._last_check = time.time()
        return result

    def _spec(self, task: Task, modality: Modality) -> TaskSpec:
        spec = self.registry.get(task)
        if spec is None or spec.modality is not modality:
            raise AIUnsupportedTaskError(f"task {task.value} does not accept {modality.value} input")
        if not spec.enabled:
            raise AIUnsupportedTaskError(f"{task.value} is unavailable: {spec.disabled_reason}")
        return spec

    def _with_fallback(self, spec: TaskSpec, call: Any) -> AIResult:
        try:
            return call(spec, False)
        except _FALLBACK_ON as exc:
            fb = self.registry.get(spec.fallback) if spec.fallback else None
            if fb is None or not fb.enabled or fb.modality is not spec.modality:
                raise
            logger.warning("task %s: primary model failed (%s); using fallback", spec.task.value, exc.code)
            return call(fb, True)

    # -- text -------------------------------------------------------------
    def run_text(self, task: Task, messages: list[dict[str, Any]], schema: type[M] | None = None) -> AIResult:
        """Run a text task; with ``schema`` the response must parse and validate."""
        spec = self._spec(task, Modality.TEXT)

        def call(sp: TaskSpec, used_fb: bool) -> AIResult:
            out = self.client.respond(
                sp.model, messages, retries=sp.max_retries, timeout=sp.timeout_seconds, max_tokens=sp.max_tokens)
            parsed = None
            if schema is not None:
                try:
                    parsed = schema.model_validate(extract_json(out["text"]))
                except (ValueError, ValidationError) as exc:
                    raise AIInvalidResponseError(
                        "model output failed schema validation", provider=sp.provider.value, model=sp.model) from exc
            return AIResult(task.value, sp.provider.value, out["model"], used_fb, out["request_id"],
                            out["usage"], text=out["text"], parsed=parsed)

        return self._with_fallback(spec, call)

    # -- audio ------------------------------------------------------------
    def transcribe(self, filename: str, content: bytes, content_type: str | None, language: str | None = None) -> dict[str, Any]:
        """Transcribe a WAV recording with Muse Voice Transcribe. Audio is never persisted."""
        spec = self._spec(Task.TRANSCRIPTION, Modality.AUDIO)
        validate_audio(content, content_type, self.settings.max_audio_bytes)
        bias = [_LANGUAGE_NAMES.get(language.lower().split("-")[0], language)] if language else None
        out = self.client.transcribe(
            spec.model, filename or "recording.wav", content, retries=spec.max_retries,
            timeout=spec.timeout_seconds, language_bias=bias)
        if not out["text"]:
            raise AIInvalidInputError("no speech was detected in the recording")
        return {**out, "language": None, "provider": spec.provider.value, "task": spec.task.value}

    # -- vision -----------------------------------------------------------
    def analyze_image(self, prompt: str, image: bytes, content_type: str | None) -> AIResult:
        """Visual investigation with Muse Spark's image understanding."""
        spec = self._spec(Task.VISION, Modality.VISION)
        mime = validate_image(image, content_type, self.settings.max_image_bytes)
        out = self.client.vision_respond(
            spec.model, prompt, image, mime, retries=spec.max_retries, timeout=spec.timeout_seconds,
            max_tokens=spec.max_tokens)
        return AIResult(spec.task.value, spec.provider.value, out["model"], False, out["request_id"], out["usage"],
                        text=out["text"])

    # -- segmentation -------------------------------------------------------
    def segment_image(self, image: bytes, content_type: str | None, concept: str) -> dict[str, Any]:
        """Text-prompted SAM 3.1 segmentation of one image: boxes and pixel masks for one short noun phrase.

        An unchanged (image, concept) pair is served from a small in-process cache so credits are not spent twice.
        A completed request with no match returns ``count == 0``; an API failure raises, it never looks like success.
        """
        spec = self._spec(Task.SEGMENTATION, Modality.SEGMENTATION)
        concept = (concept or "").strip()
        if not concept or len(concept) > 120:
            raise AIInvalidInputError("provide one short noun phrase (1-120 characters) naming the object to segment")
        mime = validate_image(image, content_type, self.settings.max_image_bytes)
        key = hashlib.sha256(image).hexdigest() + "|" + concept.lower() + "|" + spec.model
        with self._lock:
            cached = self._segments.get(key)
            if cached is not None:
                self._segments.move_to_end(key)
                return {**cached, "cached": True}
        out = self.client.segment(spec.model, concept, image, mime, retries=spec.max_retries, timeout=spec.timeout_seconds)
        result = {"task": spec.task.value, "provider": spec.provider.value, "model": spec.model, "concept": concept,
                  "cached": False, **out}
        with self._lock:
            self._segments[key] = result
            while len(self._segments) > SEGMENT_CACHE_SIZE:
                self._segments.popitem(last=False)
        return result


def _error_state(exc: AIError) -> str:
    if isinstance(exc, AIConfigurationError):
        return "key_missing"
    if isinstance(exc, AIQuotaError):
        return "insufficient_credits"
    if isinstance(exc, AIRateLimitError):
        return "rate_limited"
    if isinstance(exc, AIModelUnavailableError):
        return "model_unavailable"
    if isinstance(exc, AIAuthError):
        return "authentication_failed"
    return "network_failure" if isinstance(exc, (AIProviderUnavailableError, AITimeoutError)) else "error"


@lru_cache(maxsize=1)
def get_ai_service() -> AIService:
    """Process-wide service built from the environment (overridable in tests)."""
    return AIService(AISettings.from_env())


__all__ = [
    "AIConfigurationError", "AIError", "AIResult", "AIService", "extract_json", "get_ai_service",
    "validate_audio", "validate_image",
]
