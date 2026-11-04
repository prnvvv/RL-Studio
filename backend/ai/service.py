"""Task-routed hosted AI service.

Only the model registered for a task is invoked. A fallback is used only when it
is registered, enabled, and modality-compatible, and the model actually used is
always reported. Output is advisory: nothing here decides a verification verdict.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .clients import GroqClient, HuggingFaceClient, KeyPool
from .errors import (
    AIConfigurationError,
    AIError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIPayloadTooLargeError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
    AIUnsupportedTaskError,
)
from .registry import Modality, Provider, Task, TaskSpec, build_registry
from .settings import AISettings

logger = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)

#: errors after which trying the (compatible) fallback model is reasonable
_FALLBACK_ON = (AIRateLimitError, AITimeoutError, AIProviderUnavailableError, AIModelUnavailableError)

# magic-byte signatures for accepted audio containers
_AUDIO_SIGNATURES: dict[str, tuple[tuple[int, bytes], ...]] = {
    "audio/webm": ((0, b"\x1a\x45\xdf\xa3"),),
    "audio/ogg": ((0, b"OggS"),),
    "audio/wav": ((0, b"RIFF"), (8, b"WAVE")),
    "audio/mpeg": ((0, b"ID3"), (0, b"\xff\xfb"), (0, b"\xff\xf3"), (0, b"\xff\xf2")),
    "audio/mp4": ((4, b"ftyp"),),
    "audio/flac": ((0, b"fLaC"),),
}
_MIME_ALIASES = {
    "audio/x-wav": "audio/wav", "audio/wave": "audio/wav", "audio/mp3": "audio/mpeg",
    "audio/x-m4a": "audio/mp4", "audio/m4a": "audio/mp4", "video/webm": "audio/webm",
    "audio/x-flac": "audio/flac", "video/mp4": "audio/mp4",
}
_IMAGE_SIGNATURES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}


def normalize_mime(content_type: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    return _MIME_ALIASES.get(base, base)


def validate_audio(content: bytes, content_type: str | None, max_bytes: int) -> str:
    """Validate size, MIME type and magic bytes; returns the normalized MIME type."""
    if not content:
        raise AIInvalidInputError("the audio recording is empty")
    if len(content) > max_bytes:
        raise AIPayloadTooLargeError(f"the audio file exceeds the {max_bytes // (1024 * 1024)} MB limit")
    mime = normalize_mime(content_type)
    sigs = _AUDIO_SIGNATURES.get(mime)
    if sigs is None:
        raise AIInvalidInputError("unsupported audio type")
    if not any(content[off : off + len(sig)] == sig for off, sig in sigs):
        raise AIInvalidInputError("the audio content does not match its declared type")
    if mime == "audio/wav" and content[8:12] != b"WAVE":
        raise AIInvalidInputError("the audio content does not match its declared type")
    return mime


def validate_image(content: bytes, content_type: str | None, max_bytes: int) -> str:
    if not content:
        raise AIInvalidInputError("the image is empty")
    if len(content) > max_bytes:
        raise AIPayloadTooLargeError(f"the image exceeds the {max_bytes // (1024 * 1024)} MB limit")
    mime = (content_type or "").split(";")[0].strip().lower()
    sig = _IMAGE_SIGNATURES.get(mime)
    if sig is None:
        raise AIInvalidInputError("unsupported image type (PNG or JPEG required)")
    if not content.startswith(sig):
        raise AIInvalidInputError("the image content does not match its declared type")
    return mime


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
    def __init__(
        self,
        settings: AISettings,
        *,
        groq: GroqClient | None = None,
        hf: HuggingFaceClient | None = None,
    ) -> None:
        self.settings = settings
        self.registry = build_registry(settings)
        self.groq = groq or GroqClient(
            settings.groq_base_url,
            KeyPool(settings.groq_api_keys, call_limit=settings.groq_key_call_limit),
            timeout=settings.timeout_seconds,
        )
        self.hf = hf or HuggingFaceClient(
            settings.hf_router_base_url, settings.hf_token, timeout=settings.timeout_seconds
        )
        # injected clients (tests) serve every task; otherwise each model with a dedicated
        # credential gets its own client whose key pool is: dedicated key first, shared keys after.
        self._injected = groq is not None or hf is not None
        self._task_clients: dict[str, GroqClient | HuggingFaceClient] = {}

    def _keys_for(self, spec: TaskSpec) -> tuple[str, ...]:
        shared = self.settings.groq_api_keys if spec.provider is Provider.GROQ else (
            (self.settings.hf_token,) if self.settings.hf_token else ())
        own = self.settings.dedicated_keys.get(spec.key_env, "")
        return tuple(dict.fromkeys(k for k in (own, *shared) if k))

    def key_source(self, spec: TaskSpec) -> str:
        """'dedicated' (its own variable is set), 'shared', or 'none'. Never the key itself."""
        if spec.key_env and self.settings.dedicated_keys.get(spec.key_env):
            return "dedicated"
        return "shared" if self._keys_for(spec) else "none"

    # -- status -----------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """Per-task availability. Never contains credentials."""
        tasks = {}
        for t, s in self.registry.items():
            has_key = bool(self._keys_for(s))
            if not s.enabled:
                state, reason = "disabled", s.disabled_reason
            elif not has_key:
                state, reason = "unconfigured", f"{s.provider.value} credentials are not configured"
            else:
                state, reason = "configured", ""
            tasks[t.value] = {
                "provider": s.provider.value, "model": s.model or None, "modality": s.modality.value,
                "state": state, "reason": reason or None,
                "fallback": s.fallback.value if s.fallback else None,
                "api_key_variable": s.key_env or None, "api_key_source": self.key_source(s),
            }
        return {"config": self.settings.public(), "tasks": tasks, "groq_keys": self.groq.keys.stats()}

    def verify_groq_models(self) -> dict[str, bool]:
        """Check configured Groq model ids against the account's live catalogue."""
        available = self.groq.list_models()
        return {s.model: s.model in available for s in self.registry.values() if s.provider is Provider.GROQ and s.model}

    def _spec(self, task: Task, modality: Modality) -> TaskSpec:
        spec = self.registry.get(task)
        if spec is None or spec.modality is not modality:
            raise AIUnsupportedTaskError(f"task {task.value} does not accept {modality.value} input")
        if not spec.enabled:
            raise AIUnsupportedTaskError(f"{task.value} is unavailable: {spec.disabled_reason}")
        return spec

    def _client(self, spec: TaskSpec) -> GroqClient | HuggingFaceClient:
        """The client holding the credential configured for this task's model."""
        shared = self.groq if spec.provider is Provider.GROQ else self.hf
        if self._injected or not self.settings.dedicated_keys.get(spec.key_env):
            return shared
        cached = self._task_clients.get(spec.key_env)
        if cached is None:
            pool = KeyPool(self._keys_for(spec), call_limit=self.settings.groq_key_call_limit
                           if spec.provider is Provider.GROQ else 0)
            cached = (GroqClient(self.settings.groq_base_url, pool, timeout=self.settings.timeout_seconds)
                      if spec.provider is Provider.GROQ else
                      HuggingFaceClient(self.settings.hf_router_base_url, pool, timeout=self.settings.timeout_seconds))
            self._task_clients[spec.key_env] = cached
        return cached

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
    def run_text(
        self, task: Task, messages: list[dict[str, Any]], schema: type[M] | None = None
    ) -> AIResult:
        """Run a text task; with ``schema`` the response must parse and validate."""
        spec = self._spec(task, Modality.TEXT)

        def call(sp: TaskSpec, used_fb: bool) -> AIResult:
            out = self._client(sp).chat(
                sp.model, messages, retries=sp.max_retries, timeout=sp.timeout_seconds,
                max_tokens=sp.max_tokens, json_mode=schema is not None,
            )
            parsed = None
            if schema is not None:
                try:
                    parsed = schema.model_validate(json.loads(out["text"]))
                except (json.JSONDecodeError, ValidationError) as exc:
                    raise AIInvalidResponseError(
                        "model output failed schema validation", provider=sp.provider.value, model=sp.model
                    ) from exc
            return AIResult(task.value, sp.provider.value, out["model"], used_fb, out["request_id"],
                            out["usage"], text=out["text"], parsed=parsed)

        return self._with_fallback(spec, call)

    # -- audio ------------------------------------------------------------
    def transcribe(self, filename: str, content: bytes, content_type: str | None, language: str | None = None) -> dict[str, Any]:
        """Transcribe audio with the registered Whisper model. Audio is never persisted."""
        spec = self._spec(Task.TRANSCRIPTION, Modality.AUDIO)
        mime = validate_audio(content, content_type, self.settings.max_audio_bytes)
        out = self._client(spec).transcribe(
            spec.model, filename or "recording", content, mime,
            retries=spec.max_retries, timeout=spec.timeout_seconds, language=language,
        )
        if not out["text"]:
            raise AIInvalidInputError("no speech was detected in the recording")
        return {**out, "provider": spec.provider.value, "task": spec.task.value}

    # -- vision / segmentation ---------------------------------------------
    def analyze_image(self, prompt: str, image: bytes, content_type: str | None) -> AIResult:
        """Visual investigation; only dispatched to a configured vision-capable model."""
        spec = self._spec(Task.VISION, Modality.VISION)
        mime = validate_image(image, content_type, self.settings.max_image_bytes)
        if spec.provider is Provider.GROQ:
            import base64

            url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}]
            out = self._client(spec).chat(spec.model, messages, retries=spec.max_retries,
                                          timeout=spec.timeout_seconds, max_tokens=spec.max_tokens)
        else:
            out = self._client(spec).vision_chat(spec.model, prompt, image, mime, retries=spec.max_retries,
                                      timeout=spec.timeout_seconds, max_tokens=spec.max_tokens)
        return AIResult(spec.task.value, spec.provider.value, out["model"], False,
                        out["request_id"], out["usage"], text=out["text"])

    def segment_image(self, image: bytes, content_type: str | None) -> dict[str, Any]:
        spec = self._spec(Task.SEGMENTATION, Modality.SEGMENTATION)
        mime = validate_image(image, content_type, self.settings.max_image_bytes)
        url = spec.endpoint or f"https://api-inference.huggingface.co/models/{spec.model}"
        masks = self._client(spec).segment(url, image, mime, model=spec.model or None,
                                retries=spec.max_retries, timeout=spec.timeout_seconds)
        return {"task": spec.task.value, "provider": spec.provider.value, "model": spec.model or None, "masks": masks}


@lru_cache(maxsize=1)
def get_ai_service() -> AIService:
    """Process-wide service built from the environment (overridable in tests)."""
    return AIService(AISettings.from_env())


__all__ = [
    "AIConfigurationError", "AIError", "AIResult", "AIService", "get_ai_service",
    "validate_audio", "validate_image",
]
