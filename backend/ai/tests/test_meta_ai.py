"""Offline tests for the Meta Model API integration.

Mocked: only the HTTP transport (``httpx.MockTransport``) answers for api.meta.ai. The real ``AIService``, registry,
``MetaClient`` (OpenAI SDK), retry/fallback logic and the official ``meta-sam-parser`` all run. Nothing here proves
that a live Meta call works, that the key is valid, or that the account can use any model: see
``test_live_meta_ai.py`` for the opt-in tests that make real (credit-consuming) calls.
"""

from __future__ import annotations

import base64
import io
import json
import struct
import wave
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.ai.clients import MetaClient
from backend.ai.errors import (
    AIAuthError,
    AIConfigurationError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIPayloadTooLargeError,
    AIProviderUnavailableError,
    AIQuotaError,
    AIRateLimitError,
    AIUnsupportedTaskError,
)
from backend.ai.registry import Modality, Provider, Task, build_registry
from backend.ai.service import AIService, extract_json, get_ai_service, validate_audio
from backend.ai.settings import AISettings
from backend.api.routers import voice

KEY = "meta_test_secret_do_not_leak"
PNG = None  # built lazily (Pillow)


def png() -> bytes:
    from backend.ai.diagnostics import probe_image

    return probe_image()


def wav(seconds: float = 1.0, rate: int = 16000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 100) * int(rate * seconds) * channels)
    return buf.getvalue()


def settings(**env: str) -> AISettings:
    return AISettings.from_env({"MODEL_API_KEY": KEY, "META_API_MAX_RETRIES": "2", **env})


def service(handler, **env) -> AIService:
    s = settings(**env)
    sleeps: list[float] = []
    client = MetaClient(s.base_url, s.api_key, transport=httpx.MockTransport(handler), sleep=sleeps.append)
    svc = AIService(s, client=client)
    svc.sleeps = sleeps  # type: ignore[attr-defined]
    return svc


def responses_ok(text: str, model: str = "muse-spark-1.3", rid: str = "resp_1") -> httpx.Response:
    return httpx.Response(200, json={
        "id": rid, "object": "response", "created_at": 0, "model": model, "status": "completed",
        "output": [{"type": "message", "id": "m", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    })


def err(status: int, etype: str = "invalid_request_error", code: str | None = None, param: str | None = None, **kw: Any):
    return httpx.Response(status, json={"error": {"message": "x", "type": etype, "param": param, "code": code}}, **kw)


MSG = [{"role": "user", "content": "hi"}]


# --- settings / registry -------------------------------------------------------


def test_default_registry_matches_required_models():
    reg = build_registry(settings())
    for task in (Task.INTENT, Task.REQUIREMENTS, Task.GENERAL, Task.VISION):
        assert reg[task].model == "muse-spark-1.3"
    for task in (Task.ROOT_CAUSE, Task.INVESTIGATION, Task.RECOVERY_PLANNING):
        assert reg[task].model == "muse-wonder-1.0" and reg[task].preview
    assert reg[Task.IMAGE_GENERATION].model == "muse-image-1.0"
    assert reg[Task.TRANSCRIPTION].model == "muse-voice-transcribe-1.0"
    assert reg[Task.SEGMENTATION].model == "sam-3.1"
    assert all(s.provider is Provider.META and s.enabled for s in reg.values())


def test_every_model_variable_is_consumed_by_the_registry():
    env = {
        "META_INTENT_MODEL": "muse-spark-9.9", "META_REQUIREMENTS_MODEL": "muse-spark-9.8", "META_GENERAL_MODEL": "muse-spark-9.7",
        "META_ROOT_CAUSE_MODEL": "muse-wonder-9.1", "META_INVESTIGATION_MODEL": "muse-wonder-9.2",
        "META_RECOVERY_PLANNING_MODEL": "muse-wonder-9.3", "META_VISION_MODEL": "muse-spark-9.6",
        "META_IMAGE_MODEL": "muse-image-9.0", "META_VOICE_MODEL": "muse-voice-transcribe-9.0", "META_SEGMENTATION_MODEL": "sam-9.0",
    }
    reg = build_registry(settings(**env))
    got = {t: reg[t].model for t in reg}
    assert got == {
        Task.INTENT: "muse-spark-9.9", Task.REQUIREMENTS: "muse-spark-9.8", Task.GENERAL: "muse-spark-9.7",
        Task.ROOT_CAUSE: "muse-wonder-9.1", Task.INVESTIGATION: "muse-wonder-9.2", Task.RECOVERY_PLANNING: "muse-wonder-9.3",
        Task.VISION: "muse-spark-9.6", Task.IMAGE_GENERATION: "muse-image-9.0", Task.TRANSCRIPTION: "muse-voice-transcribe-9.0",
        Task.SEGMENTATION: "sam-9.0",
    }


def test_default_model_variable_drives_the_spark_tasks():
    reg = build_registry(settings(META_DEFAULT_MODEL="muse-spark-1.2"))
    assert reg[Task.INTENT].model == reg[Task.VISION].model == "muse-spark-1.2"


def test_feature_flags_disable_capabilities_with_a_reason():
    reg = build_registry(settings(META_VISION_ENABLED="false", META_IMAGE_GENERATION_ENABLED="false",
                                  META_VOICE_ENABLED="false", META_SEGMENTATION_ENABLED="false", META_WONDER_ENABLED="false"))
    for task in (Task.VISION, Task.IMAGE_GENERATION, Task.TRANSCRIPTION, Task.SEGMENTATION, Task.ROOT_CAUSE,
                 Task.INVESTIGATION, Task.RECOVERY_PLANNING):
        assert not reg[task].enabled and reg[task].disabled_reason
    assert reg[Task.INTENT].enabled  # Spark is unaffected by the Wonder switch


def test_a_model_is_never_routed_to_a_modality_it_does_not_support():
    reg = build_registry(settings(META_VISION_MODEL="sam-3.1", META_SEGMENTATION_MODEL="muse-image-1.0",
                                  META_INTENT_MODEL="muse-voice-transcribe-1.0"))
    for task in (Task.VISION, Task.SEGMENTATION, Task.INTENT):
        assert not reg[task].enabled and "does not support" in reg[task].disabled_reason


def test_fallbacks_are_only_wonder_to_spark_and_toggleable():
    reg = build_registry(settings())
    assert reg[Task.ROOT_CAUSE].fallback is Task.INTENT
    assert reg[Task.INTENT].fallback is None and reg[Task.TRANSCRIPTION].fallback is None and reg[Task.SEGMENTATION].fallback is None
    assert build_registry(settings(AI_ENABLE_FALLBACK="false"))[Task.ROOT_CAUSE].fallback is None


def test_reliability_settings_are_read_and_bounded():
    s = settings(META_API_TIMEOUT_SECONDS="45", META_API_MAX_RETRIES="5", META_API_RETRY_BACKOFF_SECONDS="0.5")
    assert (s.timeout_seconds, s.max_retries, s.retry_backoff_seconds) == (45.0, 5, 0.5)
    assert build_registry(s)[Task.INTENT].max_retries == 5
    assert settings(META_API_MAX_RETRIES="-3").max_retries == 0


def test_placeholder_key_counts_as_unconfigured():
    assert AISettings.from_env({"MODEL_API_KEY": "REPLACE_WITH_META_KEY"}).api_key == ""
    assert AISettings.from_env({"MODEL_API_KEY": "   "}).api_key == ""


def test_public_status_never_contains_secrets():
    svc = service(lambda r: responses_ok("{}"))
    status = svc.status()
    assert KEY not in json.dumps(status) and KEY not in repr(svc.settings)
    assert status["config"]["api_key_configured"] is True and status["config"]["provider"] == "meta"
    # configured is not verified
    assert status["tasks"]["intent_interpretation"]["model_access"] == "not_verified"


def test_missing_key_is_a_configuration_error_and_makes_no_call():
    calls: list[int] = []
    s = AISettings.from_env({})
    svc = AIService(s, client=MetaClient(s.base_url, s.api_key, transport=httpx.MockTransport(lambda r: calls.append(1))))
    assert svc.status()["tasks"]["intent_interpretation"]["state"] == "unconfigured"
    with pytest.raises(AIConfigurationError):
        svc.run_text(Task.INTENT, MSG)
    assert not calls


# --- wire format --------------------------------------------------------------


def test_text_goes_to_the_meta_responses_endpoint_with_a_bearer_key_and_developer_role():
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(url=str(req.url), auth=req.headers["authorization"], body=json.loads(req.content))
        return responses_ok("OK")

    res = service(handler).run_text(Task.INTENT, [{"role": "system", "content": "rules"}, {"role": "user", "content": "x"}])
    assert seen["url"] == "https://api.meta.ai/v1/responses"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "muse-spark-1.3"
    assert [m["role"] for m in seen["body"]["input"]] == ["developer", "user"]
    assert res.provider == "meta" and res.text == "OK" and res.request_id


def test_the_sdk_never_reaches_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    hosts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hosts.append(req.url.host)
        assert KEY in req.headers["authorization"]
        return responses_ok("OK")

    service(handler).run_text(Task.INTENT, MSG)
    assert hosts == ["api.meta.ai"]


def test_a_parameter_meta_rejects_is_dropped_once_and_retried():
    bodies: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        bodies.append(body)
        return err(400, param="temperature") if "temperature" in body else responses_ok("OK")

    assert service(handler).run_text(Task.INTENT, MSG).text == "OK"
    assert "temperature" in bodies[0] and "temperature" not in bodies[1] and len(bodies) == 2


def test_an_undroppable_400_is_not_retried():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return err(400, param="input")

    with pytest.raises(AIInvalidInputError):
        service(handler).run_text(Task.INTENT, MSG)
    assert len(calls) == 1


# --- credentials & errors ------------------------------------------------------


def test_auth_error_is_not_retried_and_does_not_leak_the_key():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return err(401, "authentication_error", "invalid_api_key")

    with pytest.raises(AIAuthError) as ei:
        service(handler).run_text(Task.INTENT, MSG)
    assert len(calls) == 1 and KEY not in ei.value.message and ei.value.code == "AI-002"


def test_insufficient_credits_is_a_quota_error_and_is_not_retried():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return err(402, "billing_error", "billing_not_configured")

    with pytest.raises(AIQuotaError) as ei:
        service(handler).run_text(Task.INTENT, MSG)
    assert len(calls) == 1 and ei.value.code == "AI-011" and not ei.value.retryable


def test_rate_limit_retries_are_bounded_and_honour_retry_after():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return err(429, "rate_limit_error", "rate_limit_exceeded", headers={"Retry-After": "3"})

    svc = service(handler, AI_ENABLE_FALLBACK="false")
    with pytest.raises(AIRateLimitError):
        svc.run_text(Task.INTENT, MSG)
    assert len(calls) == 3 and len(svc.sleeps) == 2  # type: ignore[attr-defined]
    assert all(3.0 <= d <= 3.25 for d in svc.sleeps)  # type: ignore[attr-defined]


def test_server_errors_retry_with_bounded_backoff():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    svc = service(handler, AI_ENABLE_FALLBACK="false")
    with pytest.raises(AIProviderUnavailableError):
        svc.run_text(Task.INTENT, MSG)
    assert len(calls) == 3


def test_timeout_is_reported():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(Exception) as ei:
        service(handler, META_API_MAX_RETRIES="0", AI_ENABLE_FALLBACK="false").run_text(Task.INTENT, MSG)
    assert ei.value.code == "AI-004"


def test_model_not_found_is_reported_as_model_unavailable():
    with pytest.raises(AIModelUnavailableError):
        service(lambda r: err(404, code="model_not_found"), AI_ENABLE_FALLBACK="false").run_text(Task.INTENT, MSG)


def test_wonder_falls_back_to_spark_and_the_fallback_is_recorded():
    models: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        model = json.loads(req.content)["model"]
        models.append(model)
        return err(404, code="model_not_found") if model == "muse-wonder-1.0" else responses_ok("ok", model)

    res = service(handler).run_text(Task.ROOT_CAUSE, MSG)
    assert models == ["muse-wonder-1.0", "muse-spark-1.3"]
    assert res.fallback_used and res.model == "muse-spark-1.3"


def test_no_fallback_on_auth_failure_or_when_disabled():
    models: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        models.append(json.loads(req.content)["model"])
        return err(401, "authentication_error")

    with pytest.raises(AIAuthError):
        service(handler).run_text(Task.ROOT_CAUSE, MSG)
    assert len(models) == 1
    with pytest.raises(AIModelUnavailableError):
        service(lambda r: err(404), AI_ENABLE_FALLBACK="false").run_text(Task.ROOT_CAUSE, MSG)


# --- structured output ---------------------------------------------------------


class Intent(BaseModel):
    behavior: str
    threshold: float | None = None


def test_structured_output_is_validated_and_tolerates_a_fence():
    reply = "```json\n" + json.dumps({"behavior": "reach goal", "threshold": None}) + "\n```"
    res = service(lambda r: responses_ok(reply)).run_text(Task.INTENT, MSG, Intent)
    assert isinstance(res.parsed, Intent) and res.parsed.threshold is None and res.provider == "meta"


@pytest.mark.parametrize("bad", ["not json", json.dumps({"wrong": 1}), json.dumps([1])])
def test_invalid_structured_output_is_rejected(bad):
    with pytest.raises(AIInvalidResponseError):
        service(lambda r: responses_ok(bad)).run_text(Task.INTENT, MSG, Intent)


def test_empty_response_is_rejected():
    with pytest.raises(AIInvalidResponseError):
        service(lambda r: responses_ok("  ")).run_text(Task.INTENT, MSG)


def test_extract_json_finds_an_object_inside_a_preamble():
    assert extract_json('Here you go: {"a": 1} thanks') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("nothing here")


# --- vision --------------------------------------------------------------------


def test_vision_sends_an_input_image_data_url_to_muse_spark():
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return responses_ok("a red square")

    res = service(handler).analyze_image("describe", png(), "image/png")
    parts = seen["input"][-1]["content"]
    assert seen["model"] == "muse-spark-1.3" and [p["type"] for p in parts] == ["input_text", "input_image"]
    assert parts[1]["image_url"].startswith("data:image/png;base64,") and res.text == "a red square"


def test_image_validation_and_disabled_vision():
    svc = service(lambda r: responses_ok("x"))
    with pytest.raises(AIInvalidInputError):
        svc.analyze_image("d", b"GIF89a....", "image/png")
    with pytest.raises(AIInvalidInputError):
        svc.analyze_image("d", png(), "image/jpeg")  # declared type must match content
    with pytest.raises(AIUnsupportedTaskError):
        service(lambda r: responses_ok("x"), META_VISION_ENABLED="false").analyze_image("d", png(), "image/png")


def test_text_task_rejects_non_text_modality():
    with pytest.raises(AIUnsupportedTaskError):
        service(lambda r: responses_ok("x"))._spec(Task.TRANSCRIPTION, Modality.TEXT)


# --- image generation / editing --------------------------------------------------


def test_image_generation_uses_the_images_endpoint_and_returns_base64():
    seen: dict[str, Any] = {}
    b64 = base64.b64encode(png()).decode()

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(path=req.url.path, body=json.loads(req.content))
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": b64, "revised_prompt": "r"}]})

    out = service(handler).generate_image("a fox")
    assert seen["path"] == "/v1/images/generations"
    assert seen["body"]["model"] == "muse-image-1.0" and seen["body"]["prompt"] == "a fox" and seen["body"]["n"] == 1
    assert out["images"][0]["b64_json"] == b64 and out["model"] == "muse-image-1.0"


def test_image_edit_is_multipart_and_no_image_data_is_an_error():
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(path=req.url.path, ctype=req.headers["content-type"], body=req.content)
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": "AAAA"}]})

    out = service(handler).edit_image("make it blue", png(), "image/png")
    assert seen["path"] == "/v1/images/edits" and seen["ctype"].startswith("multipart/form-data")
    assert b"muse-image-1.0" in seen["body"] and out["images"]
    with pytest.raises(AIInvalidResponseError):
        service(lambda r: httpx.Response(200, json={"created": 1, "data": []})).generate_image("x")


def test_image_generation_validates_input():
    svc = service(lambda r: httpx.Response(200, json={"data": []}))
    for kwargs in ({"prompt": " "}, {"prompt": "x", "n": 9}, {"prompt": "x", "output_format": "gif"}):
        with pytest.raises(AIInvalidInputError):
            svc.generate_image(**kwargs)


# --- audio -----------------------------------------------------------------------


def test_audio_validation_rules():
    assert validate_audio(wav(), "audio/wav", 10_000_000) == "audio/wav"
    assert validate_audio(wav(rate=24000), "audio/x-wav", 10_000_000) == "audio/wav"
    for content, ctype, limit in (
        (b"", "audio/wav", 1000), (b"not audio", "audio/wav", 1000), (wav(), "audio/webm", 10_000_000),
        (wav(rate=44100), "audio/wav", 10_000_000), (wav(channels=2), "audio/wav", 10_000_000),
    ):
        with pytest.raises(AIInvalidInputError):
            validate_audio(content, ctype, limit)
    with pytest.raises(AIPayloadTooLargeError):
        validate_audio(wav(), "audio/wav", 10)


def test_transcription_posts_multipart_request_and_audio_parts():
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(path=req.url.path, auth=req.headers["authorization"], ctype=req.headers["content-type"], body=req.content)
        return httpx.Response(200, json={
            "sessionId": "s1", "transcript": " the reward is wrong ", "audioDurationMs": 2500,
            "turns": [{"turnId": 1, "startMs": 0, "endMs": 2400, "transcript": "the reward is wrong", "speaker": "A"}]})

    out = service(handler).transcribe("rec.wav", wav(), "audio/wav", language="en")
    assert seen["path"] == "/v1/asr/transcribe" and seen["auth"] == f"Bearer {KEY}" and seen["ctype"].startswith("multipart/form-data")
    body = seen["body"]
    assert b'name="request"' in body and b'"audioEncoding": "WAV"' in body and b"muse-voice-transcribe-1.0" in body
    assert b'"languageBias": ["English"]' in body and b'name="audio"' in body and b"RIFF" in body
    assert out["text"] == "the reward is wrong" and out["duration"] == 2.5 and out["turns"][0]["speaker"] == "A"
    assert out["provider"] == "meta" and out["request_id"] == "s1"


def test_transcription_errors_are_typed_and_empty_speech_is_reported():
    with pytest.raises(AIInvalidInputError):
        service(lambda r: httpx.Response(200, json={"transcript": "", "turns": [], "audioDurationMs": 10})).transcribe(
            "r.wav", wav(), "audio/wav")
    with pytest.raises(AIPayloadTooLargeError):
        service(lambda r: err(413)).transcribe("r.wav", wav(), "audio/wav")
    with pytest.raises(AIQuotaError):
        service(lambda r: err(402, "billing_error")).transcribe("r.wav", wav(), "audio/wav")
    with pytest.raises(AIInvalidResponseError):
        service(lambda r: httpx.Response(200, json={"turns": []})).transcribe("r.wav", wav(), "audio/wav")


# --- SAM segmentation --------------------------------------------------------------


def sse(events: list[dict[str, Any]]) -> httpx.Response:
    body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


def sam_line(w: int = 8, h: int = 6) -> str:
    from meta_sam_parser._mask_codec import (
        _encode_raster,  # test-only fixture encoder from the official package
    )

    raster = bytes(1 if 2 <= x < 6 and 1 <= y < 5 else 0 for y in range(h) for x in range(w))
    return f"<0f>0<|box;x1=10;y1=20;x2=18;y2=26;w=64;h=48;c=0.9|><|mask;x=0;y=0;data={h},{w},{_encode_raster(raster, w, h)};c=0.9|>"


def sam_events(line: str | None) -> list[dict[str, Any]]:
    base = {"item_id": "msg_1", "output_index": 0, "content_index": 0, "sequence_number": 0}
    events: list[dict[str, Any]] = [{"type": "response.created", "response": {"id": "r", "status": "in_progress"}, "sequence_number": 0}]
    if line is not None:
        events.append({"type": "response.output_text.delta", "delta": line, **base})
        events.append({"type": "response.output_text.done", "text": line, **base})
    events.append({"type": "response.completed", "response": {"id": "r", "status": "completed"}, "sequence_number": 9})
    return events


def test_sam_returns_decoded_boxes_and_masks_from_the_official_parser():
    seen: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(path=req.url.path, body=json.loads(req.content))
        return sse(sam_events(sam_line()))

    out = service(handler).segment_image(png(), "image/png", "red square")
    assert seen["path"] == "/v1/responses" and seen["body"]["model"] == "sam-3.1" and seen["body"]["stream"] is True
    content = seen["body"]["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "red square"} and content[1]["type"] == "input_image"
    assert out["count"] == 1 and out["model"] == "sam-3.1" and out["cached"] is False
    box, mask = out["boxes"][0], out["masks"][0]
    # the wire carries inclusive corners; the official parser reports half-open right/bottom edges (x2/y2 exclusive)
    assert (box["x1"], box["y1"], box["x2"], box["y2"]) == (10, 20, 19, 27) and box["confidence"] == pytest.approx(0.9)
    assert (mask["width"], mask["height"], mask["foreground_pixels"]) == (8, 6, 16)
    from PIL import Image

    img = Image.open(io.BytesIO(base64.b64decode(mask["mask_png_base64"])))
    assert img.size == (8, 6) and img.getpixel((3, 2)) == 255 and img.getpixel((0, 0)) == 0


def test_sam_zero_matches_is_a_valid_empty_result_not_an_error():
    out = service(lambda r: sse(sam_events(None))).segment_image(png(), "image/png", "unicorn")
    assert out["count"] == 0 and out["boxes"] == [] and out["masks"] == []


def test_sam_api_failure_is_never_an_empty_success():
    with pytest.raises(AIQuotaError):
        service(lambda r: err(402, "billing_error")).segment_image(png(), "image/png", "duck")
    with pytest.raises(AIModelUnavailableError):
        service(lambda r: err(404, code="model_not_found")).segment_image(png(), "image/png", "duck")
    truncated = sam_events(sam_line())[:-1]  # stream ends without response.completed
    with pytest.raises(AIInvalidResponseError):
        service(lambda r: sse(sam_events(None)[:1])).segment_image(png(), "image/png", "duck")  # no text, never completed
    with pytest.raises(AIInvalidResponseError):
        service(lambda r: sse(truncated)).segment_image(png(), "image/png", "duck")


def test_sam_identical_requests_are_served_from_the_cache():
    calls: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return sse(sam_events(sam_line()))

    svc = service(handler)
    first = svc.segment_image(png(), "image/png", "Red Square")
    second = svc.segment_image(png(), "image/png", "red square")
    assert len(calls) == 1 and first["cached"] is False and second["cached"] is True
    svc.segment_image(png(), "image/png", "blue disc")
    assert len(calls) == 2


def test_sam_validates_the_concept_and_the_image():
    svc = service(lambda r: sse(sam_events(None)))
    for concept in ("", "  ", "x" * 200):
        with pytest.raises(AIInvalidInputError):
            svc.segment_image(png(), "image/png", concept)
    with pytest.raises(AIInvalidInputError):
        svc.segment_image(b"junk", "image/png", "duck")


# --- model catalogue ------------------------------------------------------------------


def test_verify_models_records_listed_and_not_listed():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/models"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "muse-spark-1.3", "object": "model", "created": 1, "owned_by": "meta"}]})

    svc = service(handler)
    result = svc.verify_models()
    assert result["muse-spark-1.3"]["state"] == "listed" and result["muse-wonder-1.0"]["state"] == "not_listed"
    status = svc.status()
    assert status["tasks"]["intent_interpretation"]["model_access"] == "listed" and status["last_connectivity_test"]
    assert status["tasks"]["root_cause_investigation"]["model_access"] == "not_listed"


def test_verify_models_reports_why_it_could_not_check():
    result = service(lambda r: err(401, "authentication_error")).verify_models()
    assert {v["state"] for v in result.values()} == {"authentication_failed"}
    assert KEY not in json.dumps(result)


# --- voice API ----------------------------------------------------------------------------


@pytest.fixture
def api():
    voice._hits.clear()
    app = FastAPI()
    app.include_router(voice.router)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sessionId": "s9", "transcript": " the reward is wrong ", "audioDurationMs": 1000, "turns": []})

    svc = service(handler)
    app.dependency_overrides[get_ai_service] = lambda: svc
    return TestClient(app), svc


def test_voice_endpoint_transcribes_wav_without_leaking_the_key(api):
    client, _ = api
    r = client.post("/api/v1/voice/transcribe", files={"audio": ("rec.wav", wav(), "audio/wav")})
    assert r.status_code == 200 and KEY not in r.text
    assert r.json()["text"] == "the reward is wrong" and r.json()["provider"] == "meta" and r.json()["model"] == "muse-voice-transcribe-1.0"


def test_voice_endpoint_rejects_non_wav_and_oversize_and_rate_limits(api):
    client, svc = api
    assert client.post("/api/v1/voice/transcribe", files={"audio": ("a.webm", b"\x1a\x45\xdf\xa3" + b"0" * 32, "audio/webm")}).status_code == 422
    svc.settings = settings(AI_MAX_AUDIO_BYTES="100")
    assert client.post("/api/v1/voice/transcribe", files={"audio": ("rec.wav", wav(), "audio/wav")}).status_code == 413
    voice._hits.clear()
    for _ in range(voice.RATE_LIMIT):
        client.post("/api/v1/voice/transcribe", files={"audio": ("a.wav", b"x", "audio/wav")})
    assert client.post("/api/v1/voice/transcribe", files={"audio": ("a.wav", b"x", "audio/wav")}).status_code == 429


def test_voice_status_endpoint_reports_state_without_secrets(api):
    client, _ = api
    r = client.get("/api/v1/voice/status")
    assert r.status_code == 200 and r.json()["model"] == "muse-voice-transcribe-1.0" and KEY not in r.text


def test_voice_endpoint_reports_a_missing_key_as_unavailable():
    voice._hits.clear()
    app = FastAPI()
    app.include_router(voice.router)
    s = AISettings.from_env({})
    app.dependency_overrides[get_ai_service] = lambda: AIService(s, client=MetaClient(s.base_url, s.api_key))
    r = TestClient(app).post("/api/v1/voice/transcribe", files={"audio": ("rec.wav", wav(), "audio/wav")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI-001"


# --- Meta is the only provider ----------------------------------------------------------------


def _requirements() -> set[str]:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    path = next(p for p in (root / "requirements.txt", root / "backend" / "requirements.txt") if p.is_file())
    return {ln.split("==")[0].split(";")[0].strip().lower().replace("_", "-") for ln in path.read_text(encoding="utf-8").splitlines() if "==" in ln}


def test_requirements_pin_the_meta_stack_and_exclude_other_providers_and_local_inference():
    pinned = _requirements()
    assert {"openai", "pillow", "meta-sam-parser"} <= pinned
    assert not pinned & {"groq", "huggingface-hub", "hf-xet", "transformers", "torchvision", "vllm", "ollama"}


def test_no_runtime_module_references_another_inference_provider():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    banned = ("groq", "huggingface", "hf_token", "mask2former", "qwen", "whisper", "api.openai.com")
    offenders = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        # diagnostics.py names the forbidden libraries on purpose, to assert they are never imported
        if "/tests/" in f"/{rel}" or rel in {"ai/diagnostics.py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        offenders += [f"{rel}: {word}" for word in banned if word in text]
    assert not offenders, offenders


def test_importing_the_ai_layer_loads_no_other_provider_or_local_inference_library():
    import subprocess
    import sys

    code = (
        "import backend.ai.service, backend.ai.diagnostics, backend.ai.clients, sys\n"
        "bad = [m for m in ('groq','huggingface_hub','transformers','torch','torchvision') if m in sys.modules]\n"
        "print(','.join(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[3]))
    assert out.stdout.strip() == ""
