"""Configuration validation and live connectivity probes for the hosted vision and segmentation models.

Run ``python -m backend.ai.diagnostics`` for the configuration checks, add ``--live`` to also make one small real
call to each hosted model. The vocabulary is deliberate and never blurred:

* ``NOT_CONFIGURED``          required settings are missing or still placeholders (no call is attempted)
* ``CONFIGURED``              settings look right. This is NOT evidence that anything works
* ``API_CONNECTED``           the provider answered an authenticated request
* ``MODEL_AVAILABLE``         the provider lists this exact model for this exact provider as live
* ``INFERENCE_SUCCESSFUL``    a real inference call returned usable output
* ``AUTHENTICATION_FAILED`` / ``RATE_LIMITED`` / ``PROVIDER_UNAVAILABLE``  what the provider actually said
* ``QUOTA_EXCEEDED``          the provider refused for billing reasons (HTTP 402): the account has no credits (the key and model are fine)

Secrets are never printed, logged or returned: only variable names and booleans appear in any output.
"""

from __future__ import annotations

import importlib.util
import io
import os
import sys
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
from .imaging import inspect_image
from .registry import Task, build_registry
from .settings import AISettings

NOT_CONFIGURED = "NOT_CONFIGURED"
CONFIGURED = "CONFIGURED"
API_CONNECTED = "API_CONNECTED"
MODEL_AVAILABLE = "MODEL_AVAILABLE"
INFERENCE_SUCCESSFUL = "INFERENCE_SUCCESSFUL"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
RATE_LIMITED = "RATE_LIMITED"
QUOTA_EXCEEDED = "QUOTA_EXCEEDED"

EXPECTED_ROUTER_URL = "https://router.huggingface.co/v1"
EXPECTED_QWEN_MODEL = "Qwen/Qwen2.5-VL-3B-Instruct:featherless-ai"
EXPECTED_QWEN_PROVIDER = "featherless-ai"
EXPECTED_SEGMENTATION_MODEL = "facebook/mask2former-swin-large-coco-panoptic"
EXPECTED_SEGMENTATION_PROVIDER = "hf-inference"
REQUIRED_PACKAGES = {"openai": "openai", "huggingface_hub": "huggingface_hub", "PIL": "Pillow"}
#: libraries that would mean local inference; the hosted integrations must not need (or import) them
FORBIDDEN_LOCAL_INFERENCE = ("torch", "torchvision", "transformers")
PROBE_PROMPT = "Describe this image in one sentence."


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
    backend_env, root_env = base / "backend" / ".env", base / ".env"
    return {"backend/.env": backend_env.is_file(), ".env": root_env.is_file()}


def config_checks(settings: AISettings) -> list[Check]:
    """Static checks. Passing them is CONFIGURED at most: it proves nothing about the network."""
    reg = build_registry(settings)
    vision, seg = reg[Task.VISION], reg[Task.SEGMENTATION]
    token_ok = bool(settings.hf_token)
    qwen_model = settings.vision_model
    checks = [
        Check("HF_TOKEN present and not a placeholder", token_ok,
              "set" if token_ok else "missing, empty or still a template placeholder"),
        Check("VISION_PROVIDER is huggingface", settings.vision_provider == "huggingface", settings.vision_provider or "unset"),
        Check("VISION_MODEL is configured", bool(qwen_model), "set" if qwen_model else "empty"),
        Check("VISION_MODEL is the Qwen2.5-VL-3B model", qwen_model.split(":")[0] == EXPECTED_QWEN_MODEL.split(":")[0],
              "matches" if qwen_model.split(":")[0] == EXPECTED_QWEN_MODEL.split(":")[0] else f"expected {EXPECTED_QWEN_MODEL.split(':')[0]}"),
        Check("VISION_MODEL carries the :featherless-ai provider suffix", qwen_model.endswith(f":{EXPECTED_QWEN_PROVIDER}"),
              "present" if qwen_model.endswith(f":{EXPECTED_QWEN_PROVIDER}") else f"expected the suffix :{EXPECTED_QWEN_PROVIDER}"),
        Check("HF_INFERENCE_BASE_URL is the Hugging Face router", settings.hf_router_base_url == EXPECTED_ROUTER_URL,
              "matches" if settings.hf_router_base_url == EXPECTED_ROUTER_URL else f"expected {EXPECTED_ROUTER_URL}"),
        Check("HF_SEGMENTATION_MODEL is Mask2Former panoptic", settings.hf_segmentation_model == EXPECTED_SEGMENTATION_MODEL,
              "matches" if settings.hf_segmentation_model == EXPECTED_SEGMENTATION_MODEL else
              ("empty" if not settings.hf_segmentation_model else f"expected {EXPECTED_SEGMENTATION_MODEL}")),
        Check("HF_INFERENCE_PROVIDER is hf-inference", settings.hf_inference_provider == EXPECTED_SEGMENTATION_PROVIDER,
              settings.hf_inference_provider or "unset"),
        Check("vision capability enabled in the registry", vision.enabled, "enabled" if vision.enabled else vision.disabled_reason),
        Check("segmentation capability enabled in the registry", seg.enabled, "enabled" if seg.enabled else seg.disabled_reason),
    ]
    for module, package in REQUIRED_PACKAGES.items():
        found = importlib.util.find_spec(module) is not None
        checks.append(Check(f"package {package} installed", found, "installed" if found else "missing"))
    return checks


def forbidden_imports_loaded() -> list[str]:
    """Local-inference libraries already imported into this process (the hosted path must not pull them in)."""
    return [m for m in FORBIDDEN_LOCAL_INFERENCE if m in sys.modules]


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


def _failure_state(exc: AIError) -> str:
    if isinstance(exc, AIAuthError):
        return AUTHENTICATION_FAILED
    if isinstance(exc, AIQuotaError):  # before AIRateLimitError, which it subclasses
        return QUOTA_EXCEEDED
    if isinstance(exc, AIRateLimitError):
        return RATE_LIMITED
    if isinstance(exc, (AIProviderUnavailableError, AITimeoutError, AIModelUnavailableError)):
        return PROVIDER_UNAVAILABLE
    if isinstance(exc, AIConfigurationError):
        return NOT_CONFIGURED
    return PROVIDER_UNAVAILABLE


def model_listing(token: str, model_id: str, provider: str) -> tuple[str, str]:
    """Metadata check (no inference, no weights): does the Hub list ``model_id`` as live on ``provider``?

    Returns ``(state, detail)`` with state ``MODEL_AVAILABLE``, ``PROVIDER_UNAVAILABLE`` (not listed/not live) or one
    of the authentication / rate-limit / unavailable states.
    """
    from huggingface_hub import HfApi
    from huggingface_hub.errors import HfHubHTTPError

    try:
        info = HfApi(token=token).model_info(model_id, expand=["inferenceProviderMapping"])
    except HfHubHTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return AUTHENTICATION_FAILED, "the Hub rejected the credentials"
        if status == 404:
            return PROVIDER_UNAVAILABLE, "the model id was not found on the Hub"
        if status == 429:
            return RATE_LIMITED, "the Hub rate limit was reached"
        return PROVIDER_UNAVAILABLE, f"the Hub returned HTTP {status}"
    except Exception as exc:  # noqa: BLE001 - connectivity problem, reported without details
        return PROVIDER_UNAVAILABLE, f"the Hub could not be reached ({type(exc).__name__})"
    for mapping in getattr(info, "inference_provider_mapping", None) or []:
        if getattr(mapping, "provider", None) == provider:
            status = getattr(mapping, "status", None)
            if status == "live":
                return MODEL_AVAILABLE, f"listed as live on provider {provider}"
            return PROVIDER_UNAVAILABLE, f"listed on provider {provider} but its status is {status!r}"
    return PROVIDER_UNAVAILABLE, f"the model is not listed for provider {provider}"


def probe_vision(settings: AISettings) -> Probe:
    """CONFIGURED -> MODEL_AVAILABLE -> INFERENCE_SUCCESSFUL, stopping at the first thing that is not true."""
    from .service import AIService

    probe = Probe("vision (Qwen2.5-VL-3B via featherless-ai)", NOT_CONFIGURED, "")
    service = AIService(settings)
    spec = service.registry[Task.VISION]
    keys = service._keys_for(spec)
    if not spec.enabled or not keys:
        probe.detail = spec.disabled_reason or "no Hugging Face credentials configured"
        return probe
    probe.state = CONFIGURED
    probe.reached.append(CONFIGURED)
    provider = spec.model.split(":", 1)[1] if ":" in spec.model else ""
    state, detail = model_listing(keys[0], spec.model.split(":", 1)[0], provider)
    if state != MODEL_AVAILABLE:
        probe.state, probe.detail = state, detail
        return probe
    probe.reached += [API_CONNECTED, MODEL_AVAILABLE]
    probe.state = MODEL_AVAILABLE
    try:
        result = service.analyze_image(PROBE_PROMPT, probe_image(), "image/png")
    except AIError as exc:
        probe.state, probe.detail = _failure_state(exc), f"{exc.code}: {exc.message}"
        return probe
    if not result.text.strip():
        probe.detail = "the call returned no text"
        return probe
    probe.state, probe.detail = INFERENCE_SUCCESSFUL, "the model returned a description"
    probe.reached.append(INFERENCE_SUCCESSFUL)
    probe.output_summary = {"model": result.model, "text_chars": len(result.text)}
    return probe


def probe_segmentation(settings: AISettings) -> Probe:
    from .service import AIService

    probe = Probe("segmentation (Mask2Former panoptic via hf-inference)", NOT_CONFIGURED, "")
    service = AIService(settings)
    spec = service.registry[Task.SEGMENTATION]
    keys = service._keys_for(spec)
    if not spec.enabled or not keys:
        probe.detail = spec.disabled_reason or "no Hugging Face credentials configured"
        return probe
    probe.state = CONFIGURED
    probe.reached.append(CONFIGURED)
    state, detail = model_listing(keys[0], spec.model, settings.hf_inference_provider)
    if state != MODEL_AVAILABLE:
        probe.state, probe.detail = state, detail
        return probe
    probe.reached += [API_CONNECTED, MODEL_AVAILABLE]
    probe.state = MODEL_AVAILABLE
    image = probe_image()
    try:
        result = service.segment_image(image, "image/png")
    except AIError as exc:
        probe.state, probe.detail = _failure_state(exc), f"{exc.code}: {exc.message}"
        return probe
    masks = result.get("masks") or []
    if not masks:
        probe.detail = "the call returned no segmentation data"
        return probe
    inspect_image(image, settings.max_image_bytes)
    probe.state, probe.detail = INFERENCE_SUCCESSFUL, "the model returned segmentation masks"
    probe.reached.append(INFERENCE_SUCCESSFUL)
    probe.output_summary = {"segments": len(masks), "labels": sorted({m.get("label") or "?" for m in masks})[:8]}
    return probe


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    live = "--live" in args
    settings = AISettings.from_env()
    print("env files found:", env_file_status())
    failed = 0
    for check in config_checks(settings):
        print(f"[{'ok' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
        failed += not check.ok
    print("local-inference libraries imported:", forbidden_imports_loaded() or "none")
    print("config verdict:", CONFIGURED if not failed else NOT_CONFIGURED, "(static checks only; not proof of connectivity)")
    if not live:
        print("run with --live to make real hosted API calls")
        return 1 if failed else 0
    for probe in (probe_vision(settings), probe_segmentation(settings)):
        print(f"{probe.capability}: {probe.state} - {probe.detail} reached={probe.reached} {probe.output_summary or ''}")
        failed += probe.state != INFERENCE_SUCCESSFUL
    return 1 if failed else 0


def live_tests_enabled() -> bool:
    return os.environ.get("RUN_LIVE_AI_TESTS", "").strip().lower() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
