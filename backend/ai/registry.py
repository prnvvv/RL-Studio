"""Task-specific model registry for the Meta Model API.

Each task maps to exactly one Meta-hosted model; only that model is invoked for the task. Every model id comes from
configuration (``AISettings``); none is hardcoded in business modules. A fallback exists only for the Muse Wonder
(preview) reasoning tasks, must be modality-compatible, and is always reported when used.
There is no other provider and local inference is never an option.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .settings import AISettings


class Provider(str, Enum):
    META = "meta"


class Modality(str, Enum):
    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    SEGMENTATION = "segmentation"


class Task(str, Enum):
    INTENT = "intent_interpretation"
    REQUIREMENTS = "requirement_extraction"
    GENERAL = "general_assistance"
    ROOT_CAUSE = "root_cause_investigation"
    INVESTIGATION = "investigation_assistance"
    RECOVERY_PLANNING = "recovery_planning"
    VISION = "visual_investigation"
    SEGMENTATION = "visual_segmentation"
    TRANSCRIPTION = "voice_transcription"


#: the capability each Meta model family supports; a task is rejected when its model's family cannot serve its modality
MODEL_FAMILIES: dict[str, frozenset[Modality]] = {
    "muse-spark": frozenset({Modality.TEXT, Modality.VISION}),
    "muse-wonder": frozenset({Modality.TEXT, Modality.VISION}),
    "muse-voice-transcribe": frozenset({Modality.AUDIO}),
    "sam": frozenset({Modality.SEGMENTATION}),
}


def model_family(model: str) -> str:
    """'muse-spark-1.3' -> 'muse-spark', 'sam-3.1' -> 'sam' (the part before the version number)."""
    parts = model.lower().split("-")
    while parts and parts[-1][:1].isdigit():
        parts.pop()
    return "-".join(parts)


def supports(model: str, modality: Modality) -> bool:
    return modality in MODEL_FAMILIES.get(model_family(model), frozenset())


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
    output_schema: str = ""
    #: whether the model is a preview offering whose account access must be verified
    preview: bool = False


def build_registry(s: AISettings) -> dict[Task, TaskSpec]:
    common = {"timeout_seconds": s.timeout_seconds, "max_retries": s.max_retries}
    meta = Provider.META

    def capability(model: str, modality: Modality, flag: bool, flag_reason: str) -> tuple[bool, str]:
        if not flag:
            return False, flag_reason
        if not model:
            return False, "model id not configured"
        if not supports(model, modality):
            return False, f"model {model!r} does not support {modality.value} input/output"
        return True, ""

    def text(task: Task, model: str, schema: str, fallback: Task | None = None) -> TaskSpec:
        wonder = model_family(model) == "muse-wonder"
        ok, reason = capability(model, Modality.TEXT, s.enable_wonder or not wonder,
                                "Muse Wonder (preview) is disabled by META_WONDER_ENABLED")
        return TaskSpec(
            task, meta, model, Modality.TEXT, enabled=ok, disabled_reason=reason, max_tokens=4096,
            fallback=fallback if s.enable_fallback else None, output_schema=schema, preview=wonder, **common,
        )

    # Muse Spark: the standard model for interpretation, extraction and general assistance.
    intent = text(Task.INTENT, s.intent_model, "IntentInterpretation")
    reqs = text(Task.REQUIREMENTS, s.requirements_model, "RequirementSet")
    general = text(Task.GENERAL, s.general_model, "")
    # Muse Wonder: complex multi-step investigation and planning only. May fall back to Muse Spark when Wonder
    # (a preview model) is unavailable to the account; the result then reports fallback_used and the model used.
    invest = text(Task.INVESTIGATION, s.investigation_model, "InvestigationNotes", Task.INTENT)
    root = text(Task.ROOT_CAUSE, s.root_cause_model, "RootCauseAnalysis", Task.INTENT)
    recovery = text(Task.RECOVERY_PLANNING, s.recovery_planning_model, "RecoveryPlan", Task.INTENT)

    ok, reason = capability(s.vision_model, Modality.VISION, s.enable_vision, "visual investigation disabled (META_VISION_ENABLED)")
    vision = TaskSpec(Task.VISION, meta, s.vision_model, Modality.VISION, enabled=ok, disabled_reason=reason,
                      max_tokens=2048, output_schema="VisualObservations", **common)

    ok, reason = capability(s.segmentation_model, Modality.SEGMENTATION, s.enable_segmentation,
                            "segmentation disabled (META_SEGMENTATION_ENABLED)")
    segmentation = TaskSpec(Task.SEGMENTATION, meta, s.segmentation_model, Modality.SEGMENTATION, enabled=ok,
                            disabled_reason=reason, output_schema="SegmentationMasks", **common)

    ok, reason = capability(s.voice_model, Modality.AUDIO, s.enable_voice, "voice transcription disabled (META_VOICE_ENABLED)")
    voice = TaskSpec(Task.TRANSCRIPTION, meta, s.voice_model, Modality.AUDIO, enabled=ok, disabled_reason=reason,
                     output_schema="Transcription", **common)

    specs = {t.task: t for t in (intent, reqs, general, invest, root, recovery, vision, segmentation, voice)}
    return {k: _check_fallback(v, specs) for k, v in specs.items()}


def _check_fallback(spec: TaskSpec, specs: dict[Task, TaskSpec]) -> TaskSpec:
    """Drop a fallback that is disabled, unknown, or of a different modality."""
    if spec.fallback is None:
        return spec
    fb = specs.get(spec.fallback)
    if fb is None or not fb.enabled or fb.modality != spec.modality or fb.model == spec.model:
        return replace(spec, fallback=None)
    return spec
