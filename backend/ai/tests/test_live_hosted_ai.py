"""LIVE integration tests: real calls to the hosted Qwen and Mask2Former APIs.

Opt-in only. These consume (a very small amount of) provider quota, so they are skipped unless
``RUN_LIVE_AI_TESTS=true`` is set. When enabled they make real HTTPS requests and **fail loudly** rather than skip when
a call does not succeed: authentication, rate-limit and availability problems are reported with their exact state
(``AUTHENTICATION_FAILED``, ``RATE_LIMITED``, ``PROVIDER_UNAVAILABLE`` ...), never hidden.

    RUN_LIVE_AI_TESTS=true python -m pytest backend/ai/tests/test_live_hosted_ai.py -v

The test image is generated locally (no external URL). Nothing here prints a credential.
"""

from __future__ import annotations

import pytest

from backend.ai import diagnostics as d
from backend.ai.errors import AIError
from backend.ai.service import AIService
from backend.ai.settings import AISettings

pytestmark = pytest.mark.skipif(not d.live_tests_enabled(), reason="live hosted-API tests are opt-in: set RUN_LIVE_AI_TESTS=true")


@pytest.fixture(scope="module")
def settings() -> AISettings:
    return AISettings.from_env()


def test_live_configuration_is_complete_before_any_call(settings: AISettings) -> None:
    bad = [c.name for c in d.config_checks(settings) if not c.ok]
    assert bad == [], f"NOT_CONFIGURED: {bad}"


def test_live_qwen_vision_returns_a_description(settings: AISettings) -> None:
    probe = d.probe_vision(settings)
    print(f"\nQwen vision: {probe.state} - {probe.detail} reached={probe.reached}")
    assert d.MODEL_AVAILABLE in probe.reached, f"model not available: {probe.state} - {probe.detail}"
    assert probe.state == d.INFERENCE_SUCCESSFUL, f"{probe.state}: {probe.detail}"
    assert probe.output_summary["text_chars"] > 0


def test_live_qwen_vision_answers_a_specific_question_about_the_image(settings: AISettings) -> None:
    service = AIService(settings)
    try:
        result = service.analyze_image("Name the two main colours of the shapes in this image.", d.probe_image(), "image/png")
    except AIError as exc:
        pytest.fail(f"{d._failure_state(exc)}: {exc.code} {exc.message}")
    assert result.text.strip() and result.provider == "huggingface"
    assert result.model.split(":")[0].lower().startswith("qwen")
    print(f"\nQwen replied with {len(result.text)} characters")


def test_live_mask2former_returns_segmentation_masks(settings: AISettings) -> None:
    probe = d.probe_segmentation(settings)
    print(f"\nMask2Former: {probe.state} - {probe.detail} reached={probe.reached} {probe.output_summary}")
    assert d.MODEL_AVAILABLE in probe.reached, f"model not available: {probe.state} - {probe.detail}"
    assert probe.state == d.INFERENCE_SUCCESSFUL, f"{probe.state}: {probe.detail}"
    assert probe.output_summary["segments"] >= 1


def test_live_mask2former_output_structure_is_usable(settings: AISettings) -> None:
    service = AIService(settings)
    try:
        result = service.segment_image(d.probe_image(), "image/png")
    except AIError as exc:
        pytest.fail(f"{d._failure_state(exc)}: {exc.code} {exc.message}")
    assert result["model"] == d.EXPECTED_SEGMENTATION_MODEL and result["inference_provider"] == "hf-inference"
    for mask in result["masks"]:
        assert mask["mask_png_base64"] and mask["mask_width"] > 0 and mask["mask_height"] > 0
        assert 0.0 <= mask["area_fraction"] <= 1.0
        assert mask["score"] is None or 0.0 <= mask["score"] <= 1.0
