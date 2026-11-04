"""REAL Meta Model API calls. Skipped unless ``RUN_LIVE_AI_TESTS=true`` and ``MODEL_API_KEY`` is configured.

These tests CONSUME CREDITS (each makes one small call) and are the only tests that can show a model actually works for
this account. Each model is tested independently: a Muse Spark success says nothing about Muse Wonder, Image, Voice or
SAM, and a missing-access result (404/403) or no credits (402) is reported by skipping with the typed reason, never as a pass.
"""

from __future__ import annotations

import pytest

from backend.ai import diagnostics as d
from backend.ai.errors import (
    AIAuthError,
    AIError,
    AIModelUnavailableError,
    AIQuotaError,
)
from backend.ai.registry import Task
from backend.ai.service import AIService
from backend.ai.settings import AISettings

pytestmark = pytest.mark.skipif(not d.live_tests_enabled(), reason="set RUN_LIVE_AI_TESTS=true to make real Meta calls")


@pytest.fixture(scope="module")
def settings() -> AISettings:
    s = AISettings.from_env()
    if not s.api_key:
        pytest.skip("MODEL_API_KEY is not configured")
    return s


def _call_or_skip(fn):
    try:
        return fn()
    except AIAuthError:
        pytest.fail("Meta rejected MODEL_API_KEY (authentication failed): paste a valid key into backend/.env")
    except (AIQuotaError, AIModelUnavailableError) as exc:
        pytest.skip(f"not available to this account: {exc.code} {exc.message}")
    except AIError as exc:
        pytest.fail(f"{exc.code}: {exc.message}")


def test_muse_spark_text(settings):
    out = _call_or_skip(lambda: AIService(settings).client.respond(
        settings.default_model, [{"role": "user", "content": d.PROBE_PROMPT}], max_tokens=64, retries=0))
    assert out["text"].strip()


def test_muse_spark_image_understanding(settings):
    res = _call_or_skip(lambda: AIService(settings).analyze_image(d.PROBE_IMAGE_PROMPT, d.probe_image(), "image/png"))
    assert res.text.strip()


def test_muse_wonder_is_verified_without_fallback(settings):
    svc = AIService(settings)
    spec = svc.registry[Task.ROOT_CAUSE]
    out = _call_or_skip(lambda: svc.client.respond(
        spec.model, [{"role": "user", "content": d.PROBE_PROMPT}], max_tokens=64, retries=0))
    assert out["text"].strip()


def test_sam_segmentation(settings):
    out = _call_or_skip(lambda: AIService(settings).segment_image(d.probe_image(), "image/png", "circle"))
    assert out["count"] >= 0 and out["model"] == settings.segmentation_model


def test_voice_transcribe_api_answers(settings):
    """A synthetic tone has no speech, so success here proves the endpoint and key only, not transcription quality."""
    svc = AIService(settings)

    def call() -> None:
        try:
            svc.transcribe("probe.wav", d.probe_audio(), "audio/wav")
        except AIError as exc:
            if not exc.message.startswith("no speech"):  # "no speech" means the API answered
                raise

    _call_or_skip(call)
