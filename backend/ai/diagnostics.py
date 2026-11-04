"""Configuration validation and live connectivity probes for the Meta Model API.

Run ``python -m backend.ai.diagnostics`` for the static configuration checks. Add ``--live`` to also make small real
calls (these CONSUME CREDITS); ``--live --only spark,sam`` limits which models are exercised. Each model is probed
independently: a Muse Spark success proves nothing about Muse Wonder, Voice or SAM. The vocabulary is
deliberate and never blurred:

* ``NOT_CONFIGURED``          required settings are missing or still placeholders (no call is attempted)
* ``CONFIGURED``              settings look right. This is NOT evidence that anything works
* ``MODEL_AVAILABLE``         the key's live model catalogue (GET /models) lists this exact model
* ``API_CONNECTED``           the provider answered an authenticated request but produced nothing to judge
* ``INFERENCE_SUCCESSFUL``    a real inference call returned usable output
* ``AUTHENTICATION_FAILED`` / ``RATE_LIMITED`` / ``PROVIDER_UNAVAILABLE`` / ``MODEL_UNAVAILABLE``  what Meta actually said
* ``QUOTA_EXCEEDED``          Meta refused for billing reasons (HTTP 402): no credits (the key and model may be fine)

Secrets are never printed, logged or returned: only variable names and booleans appear in any output.
"""

from __future__ import annotations

import importlib.util
import io
import os
import struct
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import (
    AIAuthError,
    AIConfigurationError,
    AIError,
    AIModelUnavailableError,
    AIProviderUnavailableError,
    AIQuotaError,
    AIRateLimitError,
    AITimeoutError,
)
from .registry import Task, build_registry
from .settings import DEFAULT_BASE_URL, AISettings

NOT_CONFIGURED = "NOT_CONFIGURED"
CONFIGURED = "CONFIGURED"
API_CONNECTED = "API_CONNECTED"
MODEL_AVAILABLE = "MODEL_AVAILABLE"
INFERENCE_SUCCESSFUL = "INFERENCE_SUCCESSFUL"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
RATE_LIMITED = "RATE_LIMITED"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"

REQUIRED_PACKAGES = {"openai": "openai", "meta_sam_parser": "meta-sam-parser", "PIL": "Pillow"}
#: libraries that would mean local inference or another provider; the Meta-only runtime must not import them
FORBIDDEN_IMPORTS = ("torch", "torchvision", "transformers", "huggingface_hub", "groq")
PROBE_PROMPT = "Reply with the single word OK."
PROBE_IMAGE_PROMPT = "Describe this image in one sentence."
ALL_PROBES = ("spark", "wonder", "voice", "sam")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Probe:
    capability: str
    state: str
    detail: str
    reached: list[str] = field(default_factory=list)
    output_summary: dict[str, Any] = field(default_factory=dict)


def env_file_status(root: Path | None = None) -> dict[str, Any]:
    """Where the backend loads configuration from, without reading any value."""
    base = root or Path(__file__).resolve().parents[2]
    return {"backend/.env": (base / "backend" / ".env").is_file(), ".env": (base / ".env").is_file()}


def config_checks(settings: AISettings) -> list[Check]:
    """Static checks. Passing them is CONFIGURED at most: it proves nothing about the network."""
    reg = build_registry(settings)
    key_ok = bool(settings.api_key)
    checks = [
        Check("MODAL_API_KEY present and not a placeholder", key_ok,
              "set" if key_ok else "missing, empty or still a template placeholder"),
        Check("META_API_BASE_URL is the Meta Model API", settings.base_url == DEFAULT_BASE_URL,
              "matches" if settings.base_url == DEFAULT_BASE_URL else f"expected {DEFAULT_BASE_URL}"),
    ]
    for task, spec in reg.items():
        checks.append(Check(f"{task.value}: {spec.model or 'no model'}", spec.enabled,
                            "enabled" if spec.enabled else spec.disabled_reason))
    for module, package in REQUIRED_PACKAGES.items():
        found = importlib.util.find_spec(module) is not None
        checks.append(Check(f"package {package} installed", found, "installed" if found else "missing"))
    return checks


def forbidden_imports_loaded() -> list[str]:
    """Local-inference or other-provider libraries already imported into this process."""
    return [m for m in FORBIDDEN_IMPORTS if m in sys.modules]


def probe_image() -> bytes:
    """A small controlled test image (generated, not downloaded): a red square and a blue disc on white."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (160, 160), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((16, 24, 76, 84), fill=(200, 30, 30))
    draw.ellipse((88, 80, 148, 140), fill=(30, 60, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def probe_audio() -> bytes:
    """One second of a 440 Hz tone as mono 16-bit 16 kHz WAV. It contains no speech: it can only prove the API answers."""
    import math

    rate = 16000
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return buf.getvalue()


def _failure_state(exc: AIError) -> str:
    if isinstance(exc, AIAuthError):
        return AUTHENTICATION_FAILED
    if isinstance(exc, AIQuotaError):  # before AIRateLimitError, which it subclasses
        return QUOTA_EXCEEDED
    if isinstance(exc, AIRateLimitError):
        return RATE_LIMITED
    if isinstance(exc, AIModelUnavailableError):
        return MODEL_UNAVAILABLE
    if isinstance(exc, (AIProviderUnavailableError, AITimeoutError)):
        return PROVIDER_UNAVAILABLE
    if isinstance(exc, AIConfigurationError):
        return NOT_CONFIGURED
    return PROVIDER_UNAVAILABLE


def _text_judge(result: Any) -> tuple[str, str, dict[str, Any]]:
    text = result["text"] if isinstance(result, dict) else result.text
    model = result["model"] if isinstance(result, dict) else result.model
    if text.strip():
        return INFERENCE_SUCCESSFUL, "the model replied", {"model": model, "text_chars": len(text)}
    return API_CONNECTED, "the call returned no text", {}


def _run(name: str, task: Task, service: Any, listed: dict[str, dict[str, str]], call: Any, judge: Any) -> Probe:
    """CONFIGURED -> MODEL_AVAILABLE -> INFERENCE_SUCCESSFUL, stopping at the first thing that is not true."""
    probe = Probe(name, NOT_CONFIGURED, "")
    spec = service.registry[task]
    if not spec.enabled or not service.client.configured:
        probe.detail = spec.disabled_reason or "MODAL_API_KEY is not configured"
        return probe
    probe.state = CONFIGURED
    probe.reached.append(CONFIGURED)
    access = listed.get(spec.model, {})
    if access.get("state") == "listed":
        probe.reached.append(MODEL_AVAILABLE)
        probe.state = MODEL_AVAILABLE
    try:
        result = call(spec)
    except AIError as exc:
        probe.state, probe.detail = _failure_state(exc), f"{exc.code}: {exc.message}"
        return probe
    probe.reached.append(API_CONNECTED)
    state, detail, summary = judge(result)
    probe.state, probe.detail, probe.output_summary = state, detail, summary
    if state == INFERENCE_SUCCESSFUL:
        probe.reached.append(INFERENCE_SUCCESSFUL)
    return probe


def run_probes(settings: AISettings, only: tuple[str, ...] = ALL_PROBES) -> list[Probe]:
    """Real Meta calls, one per selected model. Consumes credits."""
    from .service import AIService

    service = AIService(settings)
    listed = service.verify_models() if service.client.configured else {}

    def _ask(sp: Any) -> dict[str, Any]:
        return service.client.respond(sp.model, [{"role": "user", "content": PROBE_PROMPT}], max_tokens=64, retries=0)

    probes: list[Probe] = []
    if "spark" in only:
        probes.append(_run("Muse Spark (text)", Task.INTENT, service, listed, _ask, _text_judge))
        probes.append(_run("Muse Spark (image understanding)", Task.VISION, service, listed,
                           lambda sp: service.analyze_image(PROBE_IMAGE_PROMPT, probe_image(), "image/png"), _text_judge))
    if "wonder" in only:
        # called directly (no fallback) so a Spark success can never be reported as Wonder access
        probes.append(_run("Muse Wonder (preview reasoning)", Task.ROOT_CAUSE, service, listed, _ask, _text_judge))
    if "voice" in only:
        def voice_judge(r: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
            if r["text"]:
                return INFERENCE_SUCCESSFUL, "speech was transcribed", {"chars": len(r["text"])}
            return API_CONNECTED, "the API answered; the synthetic tone fixture contains no speech to transcribe", {}

        def voice_call(sp: Any) -> dict[str, Any]:
            try:
                return service.transcribe("probe.wav", probe_audio(), "audio/wav")
            except AIError as exc:
                if exc.message.startswith("no speech"):
                    return {"text": ""}
                raise

        probes.append(_run("Muse Voice Transcribe", Task.TRANSCRIPTION, service, listed, voice_call, voice_judge))
    if "sam" in only:
        probes.append(_run("SAM 3.1 (segmentation)", Task.SEGMENTATION, service, listed,
                           lambda sp: service.segment_image(probe_image(), "image/png", "circle"),
                           lambda r: (INFERENCE_SUCCESSFUL, "segmentation data was returned",
                                      {"objects": r["count"], "masks": len(r["masks"])}) if r["count"]
                           else (API_CONNECTED, "the request completed with zero matches", {"objects": 0})))
    return probes


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    live = "--live" in args
    only = ALL_PROBES
    if "--only" in args and args.index("--only") + 1 < len(args):
        only = tuple(p.strip() for p in args[args.index("--only") + 1].split(",") if p.strip() in ALL_PROBES)
    settings = AISettings.from_env()
    print("env files found:", env_file_status())
    failed = 0
    for check in config_checks(settings):
        print(f"[{'ok' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
        failed += not check.ok
    print("forbidden libraries imported:", forbidden_imports_loaded() or "none")
    print("config verdict:", CONFIGURED if not failed else NOT_CONFIGURED, "(static checks only; not proof of connectivity)")
    if not live:
        print("run with --live to make real Meta API calls (consumes credits)")
        return 1 if failed else 0
    for probe in run_probes(settings, only):
        print(f"{probe.capability}: {probe.state} - {probe.detail} reached={probe.reached} {probe.output_summary or ''}")
        failed += probe.state != INFERENCE_SUCCESSFUL
    return 1 if failed else 0


def live_tests_enabled() -> bool:
    return os.environ.get("RUN_LIVE_AI_TESTS", "").strip().lower() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
