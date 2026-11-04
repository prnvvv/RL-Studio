"""Environment-driven AI configuration. Secrets are never exposed via ``public()``."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


def _bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value and value.strip() else default
    except ValueError:
        return default


def _str(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or default).strip()


@dataclass(frozen=True)
class AISettings:
    groq_api_key: str
    hf_token: str
    groq_base_url: str
    hf_router_base_url: str
    intent_model: str
    requirements_model: str
    root_cause_model: str
    investigation_model: str
    transcription_model: str
    vision_provider: str
    vision_model: str
    groq_vision_model: str
    hf_inference_provider: str
    hf_segmentation_model: str
    hf_segmentation_endpoint: str
    timeout_seconds: float
    max_retries: int
    enable_fallback: bool
    enable_visual: bool
    enable_segmentation: bool
    enable_voice: bool
    log_prompts: bool
    log_responses: bool
    max_audio_bytes: int
    max_image_bytes: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AISettings:
        if env is None:
            # populate os.environ from the gitignored backend/.env or root .env (real env vars win)
            from pathlib import Path

            from dotenv import load_dotenv

            root = Path(__file__).resolve().parents[2]
            for candidate in (root / "backend" / ".env", root / ".env"):
                load_dotenv(candidate, override=False)
        e = os.environ if env is None else env
        return cls(
            groq_api_key=_str(e, "GROQ_API_KEY"),
            hf_token=_str(e, "HF_TOKEN"),
            groq_base_url=_str(e, "GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/"),
            hf_router_base_url=_str(e, "HF_INFERENCE_BASE_URL", "https://router.huggingface.co/v1").rstrip("/"),
            intent_model=_str(e, "GROQ_INTENT_MODEL", "openai/gpt-oss-20b"),
            requirements_model=_str(e, "GROQ_REQUIREMENTS_MODEL", "openai/gpt-oss-20b"),
            root_cause_model=_str(e, "GROQ_ROOT_CAUSE_MODEL", "openai/gpt-oss-120b"),
            investigation_model=_str(e, "GROQ_INVESTIGATION_MODEL", "openai/gpt-oss-120b"),
            transcription_model=_str(e, "GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"),
            vision_provider=_str(e, "VISION_PROVIDER", "huggingface").lower(),
            vision_model=_str(e, "VISION_MODEL"),
            groq_vision_model=_str(e, "GROQ_VISION_MODEL"),
            hf_inference_provider=_str(e, "HF_INFERENCE_PROVIDER"),
            hf_segmentation_model=_str(e, "HF_SEGMENTATION_MODEL"),
            hf_segmentation_endpoint=_str(e, "HF_SEGMENTATION_ENDPOINT"),
            timeout_seconds=float(_int(e.get("AI_PROVIDER_TIMEOUT_SECONDS"), 60)),
            max_retries=max(0, _int(e.get("AI_MAX_RETRIES"), 2)),
            enable_fallback=_bool(e.get("AI_ENABLE_FALLBACK"), True),
            enable_visual=_bool(e.get("AI_ENABLE_VISUAL_INVESTIGATION"), True),
            enable_segmentation=_bool(e.get("AI_ENABLE_SEGMENTATION"), True),
            enable_voice=_bool(e.get("AI_ENABLE_VOICE_TRANSCRIPTION"), True),
            log_prompts=_bool(e.get("AI_LOG_PROMPTS"), False),
            log_responses=_bool(e.get("AI_LOG_RESPONSES"), False),
            max_audio_bytes=_int(e.get("AI_MAX_AUDIO_BYTES"), 10 * 1024 * 1024),
            max_image_bytes=_int(e.get("AI_MAX_IMAGE_BYTES"), 8 * 1024 * 1024),
        )

    def public(self) -> dict[str, object]:
        """Configuration safe to return from an API: booleans instead of secrets."""
        return {
            "groq_configured": bool(self.groq_api_key),
            "huggingface_configured": bool(self.hf_token),
            "fallback_enabled": self.enable_fallback,
            "voice_enabled": self.enable_voice,
            "visual_enabled": self.enable_visual,
            "segmentation_enabled": self.enable_segmentation,
        }
