"""Environment-driven AI configuration for the Meta Model API. Secrets are never exposed via ``public()``.

One shared credential (``MODEL_API_KEY``) serves every Meta-hosted model. Every model identifier, feature flag and
reliability setting below is read from the environment and consumed by ``registry.build_registry``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://api.meta.ai/v1"


def _bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value and value.strip() else default
    except ValueError:
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value and value.strip() else default
    except ValueError:
        return default


def _str(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or default).strip()


_PLACEHOLDER_PREFIXES = ("REPLACE_WITH", "YOUR_", "<", "CHANGE_ME")


def _secret(env: Mapping[str, str], name: str) -> str:
    """A credential value; unfilled template placeholders count as 'not configured'."""
    value = _str(env, name)
    return "" if value.upper().startswith(_PLACEHOLDER_PREFIXES) else value


@dataclass(frozen=True)
class AISettings:
    base_url: str
    default_model: str
    intent_model: str
    requirements_model: str
    general_model: str
    root_cause_model: str
    investigation_model: str
    recovery_planning_model: str
    vision_model: str
    image_model: str
    voice_model: str
    segmentation_model: str
    enable_vision: bool
    enable_image_generation: bool
    enable_voice: bool
    enable_segmentation: bool
    enable_wonder: bool
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    enable_fallback: bool
    log_prompts: bool
    log_responses: bool
    max_audio_bytes: int
    max_image_bytes: int
    #: the one shared Meta credential. Never exposed (repr/public()).
    api_key: str = field(default="", repr=False)

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
        default_model = _str(e, "META_DEFAULT_MODEL", "muse-spark-1.3")

        def model(name: str, default: str) -> str:
            return _str(e, name, default)

        spark = default_model
        return cls(
            api_key=_secret(e, "MODEL_API_KEY"),
            base_url=_str(e, "META_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            default_model=default_model,
            intent_model=model("META_INTENT_MODEL", spark),
            requirements_model=model("META_REQUIREMENTS_MODEL", spark),
            general_model=model("META_GENERAL_MODEL", spark),
            root_cause_model=model("META_ROOT_CAUSE_MODEL", "muse-wonder-1.0"),
            investigation_model=model("META_INVESTIGATION_MODEL", "muse-wonder-1.0"),
            recovery_planning_model=model("META_RECOVERY_PLANNING_MODEL", "muse-wonder-1.0"),
            vision_model=model("META_VISION_MODEL", spark),
            image_model=model("META_IMAGE_MODEL", "muse-image-1.0"),
            voice_model=model("META_VOICE_MODEL", "muse-voice-transcribe-1.0"),
            segmentation_model=model("META_SEGMENTATION_MODEL", "sam-3.1"),
            enable_vision=_bool(e.get("META_VISION_ENABLED"), True),
            enable_image_generation=_bool(e.get("META_IMAGE_GENERATION_ENABLED"), True),
            enable_voice=_bool(e.get("META_VOICE_ENABLED"), True),
            enable_segmentation=_bool(e.get("META_SEGMENTATION_ENABLED"), True),
            enable_wonder=_bool(e.get("META_WONDER_ENABLED"), True),
            timeout_seconds=max(1.0, _float(e.get("META_API_TIMEOUT_SECONDS"), 90.0)),
            max_retries=max(0, _int(e.get("META_API_MAX_RETRIES"), 2)),
            retry_backoff_seconds=max(0.0, _float(e.get("META_API_RETRY_BACKOFF_SECONDS"), 1.0)),
            # Muse Wonder is a preview model: when it is unavailable, its tasks may fall back to Muse Spark.
            # Both are Meta models; the model actually used is always reported (never silent).
            enable_fallback=_bool(e.get("AI_ENABLE_FALLBACK"), True),
            log_prompts=_bool(e.get("AI_LOG_PROMPTS"), False),
            log_responses=_bool(e.get("AI_LOG_RESPONSES"), False),
            max_audio_bytes=_int(e.get("AI_MAX_AUDIO_BYTES"), 10 * 1024 * 1024),
            max_image_bytes=_int(e.get("AI_MAX_IMAGE_BYTES"), 8 * 1024 * 1024),
        )

    def public(self) -> dict[str, object]:
        """Configuration safe to return from an API: booleans instead of secrets."""
        return {
            "provider": "meta",
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "api_key_variable": "MODEL_API_KEY",
            "fallback_enabled": self.enable_fallback,
            "vision_enabled": self.enable_vision,
            "image_generation_enabled": self.enable_image_generation,
            "voice_enabled": self.enable_voice,
            "segmentation_enabled": self.enable_segmentation,
            "wonder_enabled": self.enable_wonder,
        }
