"""Task-specific model registry.

Each task maps to exactly one hosted model; only that model is invoked for the
task. Fallbacks must be modality-compatible and are recorded when used.
Local inference is never an option: every provider here is a hosted API.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .settings import AISettings


class Provider(str, Enum):
    GROQ = "groq"
    HUGGINGFACE = "huggingface"


class Modality(str, Enum):
    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    SEGMENTATION = "segmentation"


class Task(str, Enum):
    INTENT = "intent_interpretation"
    REQUIREMENTS = "requirement_extraction"
    ROOT_CAUSE = "root_cause_investigation"
    INVESTIGATION = "investigation_assistance"
    VISION = "visual_investigation"
    SEGMENTATION = "visual_segmentation"
    TRANSCRIPTION = "voice_transcription"


@dataclass(frozen=True)
class TaskSpec:
    task: Task
    provider: Provider
    model: str
    modality: Modality
    timeout_seconds: float
    max_retries: int
    enabled: bool
    disabled_reason: str = ""
    max_tokens: int | None = None
    #: task whose spec serves as fallback (must share modality and be enabled)
    fallback: Task | None = None
    endpoint: str = ""
    output_schema: str = ""
    #: name of the env var holding this model's dedicated credential (falls back to the shared one)
    key_env: str = ""


def build_registry(s: AISettings) -> dict[Task, TaskSpec]:
    common = {"timeout_seconds": s.timeout_seconds, "max_retries": s.max_retries}
    groq = Provider.GROQ

    def text(task: Task, model: str, schema: str, key_env: str, fallback: Task | None = None) -> TaskSpec:
        return TaskSpec(
            task, groq, model, Modality.TEXT, enabled=bool(model), max_tokens=4096,
            disabled_reason="" if model else "model id not configured",
            fallback=fallback if s.enable_fallback else None, output_schema=schema, key_env=key_env, **common,
        )

    # Original design: Meta Muse Spark for intent interpretation. Replaced with Groq-hosted
    # GPT-OSS 20B because Meta API access/free credits were unavailable.
    intent = text(Task.INTENT, s.intent_model, "IntentInterpretation", "GROQ_INTENT_API_KEY")
    # Original design: Meta Muse Spark for structured requirement extraction. Replaced with
    # Groq-hosted GPT-OSS 20B because Meta API access/free credits were unavailable.
    reqs = text(Task.REQUIREMENTS, s.requirements_model, "RequirementSet", "GROQ_REQUIREMENTS_API_KEY")
    # Original design: Meta Muse Wonder for investigation assistance. Replaced with
    # Groq-hosted GPT-OSS 120B because Meta API access/free credits were unavailable.
    invest = text(Task.INVESTIGATION, s.investigation_model, "InvestigationNotes", "GROQ_INVESTIGATION_API_KEY", Task.INTENT)
    # Original design: Meta Muse Wonder for root-cause investigation. Replaced with
    # Groq-hosted GPT-OSS 120B because Meta API access/free credits were unavailable.
    root = text(Task.ROOT_CAUSE, s.root_cause_model, "RootCauseAnalysis", "GROQ_ROOT_CAUSE_API_KEY", Task.INTENT)

    # Original design: Meta Muse Image for visual environment debugging. Replaced with a hosted
    # vision-capable model because Meta API access/free credits were unavailable.
    if s.vision_provider == "groq":
        v_provider, v_model, v_key = Provider.GROQ, s.groq_vision_model, "GROQ_VISION_API_KEY"
    else:
        v_provider, v_model, v_key = Provider.HUGGINGFACE, s.vision_model, "HF_VISION_API_KEY"
    vision = TaskSpec(
        Task.VISION, v_provider, v_model, Modality.VISION,
        enabled=s.enable_visual and bool(v_model),
        disabled_reason=(
            "visual investigation disabled" if not s.enable_visual
            else "no verified vision model configured (set VISION_MODEL or GROQ_VISION_MODEL)"
        ),
        max_tokens=2048, output_schema="VisualObservations", key_env=v_key, **common,
    )

    # Original design: Meta SAM 3.1 for visual segmentation. Using a hosted Hugging Face API
    # implementation because local inference is not permitted and Meta API access/free credits
    # were unavailable.
    segmentation = TaskSpec(
        Task.SEGMENTATION, Provider.HUGGINGFACE, s.hf_segmentation_model, Modality.SEGMENTATION,
        enabled=s.enable_segmentation and bool(s.hf_segmentation_model or s.hf_segmentation_endpoint),
        disabled_reason=(
            "segmentation disabled" if not s.enable_segmentation
            else "no hosted segmentation model/endpoint configured"
        ),
        endpoint=s.hf_segmentation_endpoint, output_schema="SegmentationMasks",
        key_env="HF_SEGMENTATION_API_KEY", **common,
    )

    # Original design: Meta Muse Voice Transcribe for voice input. Replaced with Groq Whisper
    # Large V3 Turbo because Meta API access/free credits were unavailable.
    voice = TaskSpec(
        Task.TRANSCRIPTION, groq, s.transcription_model, Modality.AUDIO,
        enabled=s.enable_voice and bool(s.transcription_model),
        disabled_reason="voice transcription disabled" if not s.enable_voice else "model id not configured",
        output_schema="Transcription", key_env="GROQ_TRANSCRIPTION_API_KEY", **common,
    )

    # Muse Glimmer / Muse Spark Open (open-weight evaluation) have no runtime task: the original
    # intent was to evaluate open-weight models on a bounded task. Candidates here would be hosted
    # open-weight models (e.g. GPT-OSS 20B on Groq) compared offline, never served locally.
    specs = {t.task: t for t in (intent, reqs, invest, root, vision, segmentation, voice)}
    return {k: _check_fallback(v, specs) for k, v in specs.items()}


def _check_fallback(spec: TaskSpec, specs: dict[Task, TaskSpec]) -> TaskSpec:
    """Drop a fallback that is disabled, unknown, or of a different modality."""
    if spec.fallback is None:
        return spec
    fb = specs.get(spec.fallback)
    if fb is None or not fb.enabled or fb.modality != spec.modality or fb.model == spec.model:
        return replace(spec, fallback=None)
    return spec
