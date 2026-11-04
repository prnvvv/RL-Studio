"""Offline tests: providers are mocked at the httpx transport; no network, no credentials."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.ai.clients import GroqClient, HuggingFaceClient, KeyPool
from backend.ai.errors import (
    AIAuthError,
    AIConfigurationError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AIUnsupportedTaskError,
)
from backend.ai.registry import Modality, Provider, Task, build_registry
from backend.ai.service import AIService, get_ai_service, validate_audio
from backend.ai.settings import AISettings
from backend.api.routers import voice

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


def settings(**env: str) -> AISettings:
    base = {"GROQ_API_KEY": "gsk_test_secret", "HF_TOKEN": "hf_test_secret"}
    return AISettings.from_env({**base, **env})


def service(handler, **env) -> AIService:
    s = settings(**env)
    transport = httpx.MockTransport(handler)
    sleeps: list[float] = []
    groq = GroqClient(
        s.groq_base_url, KeyPool(s.groq_api_keys, call_limit=s.groq_key_call_limit),
        transport=transport, sleep=sleeps.append,
    )
    hf = HuggingFaceClient(s.hf_router_base_url, s.hf_token, transport=transport, sleep=sleeps.append)
    svc = AIService(s, groq=groq, hf=hf)
    svc.sleeps = sleeps  # type: ignore[attr-defined]
    return svc


def chat_ok(content: str, model: str = "m") -> httpx.Response:
    return httpx.Response(200, json={"id": "req_1", "model": model, "choices": [{"message": {"content": content}}]})


# --- registry / settings -----------------------------------------------------


def test_default_registry_matches_required_models():
    reg = build_registry(settings())
    assert reg[Task.INTENT].model == "openai/gpt-oss-20b"
    assert reg[Task.REQUIREMENTS].model == "openai/gpt-oss-20b"
    assert reg[Task.ROOT_CAUSE].model == "openai/gpt-oss-120b"
    assert reg[Task.INVESTIGATION].model == "openai/gpt-oss-120b"
    assert reg[Task.TRANSCRIPTION].model == "whisper-large-v3-turbo"
    assert all(s.provider in (Provider.GROQ, Provider.HUGGINGFACE) for s in reg.values())


def test_vision_and_segmentation_disabled_until_configured():
    reg = build_registry(settings())
    assert not reg[Task.VISION].enabled and "VISION_MODEL" in reg[Task.VISION].disabled_reason
    assert not reg[Task.SEGMENTATION].enabled
    reg = build_registry(settings(VISION_MODEL="org/vl", HF_SEGMENTATION_MODEL="org/seg"))
    assert reg[Task.VISION].enabled and reg[Task.VISION].provider is Provider.HUGGINGFACE
    assert reg[Task.SEGMENTATION].enabled


def test_groq_vision_provider_selection():
    reg = build_registry(settings(VISION_PROVIDER="groq", GROQ_VISION_MODEL="g/vision"))
    assert reg[Task.VISION].provider is Provider.GROQ and reg[Task.VISION].model == "g/vision"


def test_fallbacks_are_modality_compatible_and_toggleable():
    reg = build_registry(settings())
    assert reg[Task.ROOT_CAUSE].fallback is Task.INTENT
    assert reg[Task.TRANSCRIPTION].fallback is None and reg[Task.VISION].fallback is None
    for spec in reg.values():
        if spec.fallback:
            assert reg[spec.fallback].modality is spec.modality
    assert build_registry(settings(AI_ENABLE_FALLBACK="false"))[Task.ROOT_CAUSE].fallback is None


def test_public_status_never_contains_secrets():
    svc = service(lambda r: chat_ok("{}"))
    dumped = json.dumps(svc.status())
    assert "gsk_test_secret" not in dumped and "hf_test_secret" not in dumped
    assert svc.status()["config"]["groq_configured"] is True


# --- credentials & errors ----------------------------------------------------


def test_missing_credentials_is_a_configuration_error():
    svc = AIService(AISettings.from_env({}))
    assert svc.status()["tasks"]["intent_interpretation"]["state"] == "unconfigured"
    with pytest.raises(AIConfigurationError):
        svc.run_text(Task.INTENT, [{"role": "user", "content": "hi"}])


def test_auth_error_is_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, text="invalid key gsk_test_secret")

    svc = service(handler)
    with pytest.raises(AIAuthError) as ei:
        svc.run_text(Task.INTENT, [{"role": "user", "content": "hi"}])
    assert len(calls) == 1
    assert "gsk_test_secret" not in ei.value.message


def test_rate_limit_with_a_single_key_fails_fast_without_hammering():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429)

    svc = service(handler, AI_ENABLE_FALLBACK="false")
    with pytest.raises(AIRateLimitError):
        svc.run_text(Task.INTENT, [{"role": "user", "content": "hi"}])
    assert len(calls) == 1  # the key is cooling down; no retry storm


def test_transient_server_errors_retry_with_bounded_backoff():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    svc = service(handler, AI_MAX_RETRIES="2", AI_ENABLE_FALLBACK="false")
    with pytest.raises(AIProviderUnavailableError):
        svc.run_text(Task.INTENT, [{"role": "user", "content": "hi"}])
    assert len(calls) == 3 and len(svc.sleeps) == 2  # type: ignore[attr-defined]


def test_timeout_is_retryable_and_reported():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    svc = service(handler, AI_MAX_RETRIES="0", AI_ENABLE_FALLBACK="false")
    with pytest.raises(Exception) as ei:
        svc.run_text(Task.INTENT, [{"role": "user", "content": "hi"}])
    assert ei.value.code == "AI-004"


def test_fallback_used_and_recorded_when_primary_unavailable():
    models = []

    def handler(req):
        model = json.loads(req.content)["model"]
        models.append(model)
        if model == "openai/gpt-oss-120b":
            return httpx.Response(404)
        return chat_ok("ok", model)

    svc = service(handler)
    res = svc.run_text(Task.ROOT_CAUSE, [{"role": "user", "content": "x"}])
    assert models == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert res.fallback_used and res.model == "openai/gpt-oss-20b"


def test_no_fallback_on_auth_failure():
    models = []

    def handler(req):
        models.append(json.loads(req.content)["model"])
        return httpx.Response(401)

    svc = service(handler)
    with pytest.raises(AIAuthError):
        svc.run_text(Task.ROOT_CAUSE, [{"role": "user", "content": "x"}])
    assert len(models) == 1


# --- structured output -------------------------------------------------------


class Intent(BaseModel):
    behavior: str
    threshold: float | None = None


def test_structured_output_is_validated():
    svc = service(lambda r: chat_ok(json.dumps({"behavior": "reach goal", "threshold": None})))
    res = svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}], Intent)
    assert isinstance(res.parsed, Intent) and res.parsed.threshold is None
    assert res.provider == "groq" and res.request_id == "req_1"


@pytest.mark.parametrize("bad", ["not json", json.dumps({"wrong": 1}), json.dumps([1])])
def test_invalid_structured_output_is_rejected(bad):
    svc = service(lambda r: chat_ok(bad))
    with pytest.raises(AIInvalidResponseError):
        svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}], Intent)


def test_empty_response_is_rejected():
    svc = service(lambda r: chat_ok("  "))
    with pytest.raises(AIInvalidResponseError):
        svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}])


# --- task routing ------------------------------------------------------------


def test_vision_task_never_routes_to_text_model_when_unconfigured():
    svc = service(lambda r: chat_ok("x"))
    with pytest.raises(AIUnsupportedTaskError):
        svc.analyze_image("describe", b"\x89PNG\r\n\x1a\n" + b"0" * 10, "image/png")


def test_text_task_rejects_non_text_modality():
    svc = service(lambda r: chat_ok("x"))
    with pytest.raises(AIUnsupportedTaskError):
        svc._spec(Task.TRANSCRIPTION, Modality.TEXT)


def test_vision_routes_image_part_to_configured_hf_model():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return chat_ok("a red square", "org/vl")

    svc = service(handler, VISION_MODEL="org/vl")
    res = svc.analyze_image("describe", b"\x89PNG\r\n\x1a\n" + b"0" * 10, "image/png")
    assert seen["model"] == "org/vl"
    assert seen["messages"][0]["content"][1]["type"] == "image_url"
    assert res.provider == "huggingface"


def test_segmentation_returns_masks_and_errors_when_none():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
    svc = service(lambda r: httpx.Response(200, json=[{"label": "agent", "score": 0.9, "mask": "AAAA"}]),
                  HF_SEGMENTATION_MODEL="org/seg")
    out = svc.segment_image(png, "image/png")
    assert out["masks"][0]["label"] == "agent"
    svc = service(lambda r: httpx.Response(200, json=[]), HF_SEGMENTATION_MODEL="org/seg")
    with pytest.raises(AIInvalidResponseError):
        svc.segment_image(png, "image/png")


def test_image_validation():
    svc = service(lambda r: chat_ok("x"), VISION_MODEL="org/vl")
    with pytest.raises(AIInvalidInputError):
        svc.analyze_image("d", b"GIF89a....", "image/png")
    with pytest.raises(AIInvalidInputError):
        svc.analyze_image("d", b"x", "image/gif")


# --- audio validation --------------------------------------------------------


def test_audio_validation_rules():
    assert validate_audio(WEBM, "audio/webm;codecs=opus", 1000) == "audio/webm"
    with pytest.raises(AIInvalidInputError):
        validate_audio(b"", "audio/webm", 1000)
    with pytest.raises(AIInvalidInputError):
        validate_audio(b"not audio", "audio/webm", 1000)
    with pytest.raises(AIInvalidInputError):
        validate_audio(WEBM, "application/pdf", 1000)
    with pytest.raises(AIInvalidInputError):
        validate_audio(WEBM, "audio/webm", 10)


# --- voice API ---------------------------------------------------------------


@pytest.fixture
def api():
    voice._hits.clear()
    app = FastAPI()
    app.include_router(voice.router)

    def groq_handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/audio/transcriptions")
        assert b"whisper-large-v3-turbo" in req.content
        assert req.headers["authorization"] == "Bearer gsk_test_secret"
        return httpx.Response(200, json={"text": " the reward is wrong ", "language": "en", "duration": 2.5})

    svc = service(groq_handler)
    app.dependency_overrides[get_ai_service] = lambda: svc
    return TestClient(app), app


def post(client, content=WEBM, ctype="audio/webm", name="r.webm"):
    return client.post("/api/v1/voice/transcribe", files={"audio": (name, content, ctype)})


def test_transcribe_success_shape(api):
    client, _ = api
    r = post(client)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "the reward is wrong"
    assert body["model"] == "whisper-large-v3-turbo" and body["provider"] == "groq"
    assert "gsk_test_secret" not in r.text


def test_transcribe_rejects_bad_uploads(api):
    client, _ = api
    assert post(client, b"").status_code == 422
    assert post(client, b"junk", "audio/webm").status_code == 422
    assert post(client, WEBM, "text/plain").status_code == 422
    assert post(client, WEBM + b"0" * (11 * 1024 * 1024)).status_code == 413


def test_transcribe_without_credentials_is_explicit_error(api):
    client, app = api
    svc = AIService(AISettings.from_env({}))
    app.dependency_overrides[get_ai_service] = lambda: svc
    r = post(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI-001"


def test_transcribe_provider_failure_is_not_success(api):
    client, app = api
    svc = service(lambda r: httpx.Response(500), AI_MAX_RETRIES="0")
    app.dependency_overrides[get_ai_service] = lambda: svc
    r = post(client)
    assert r.status_code == 503 and "text" not in r.json()


def test_transcribe_rate_limit(api):
    client, _ = api
    codes = [post(client).status_code for _ in range(voice.RATE_LIMIT + 1)]
    assert codes[-1] == 429


def test_transcribe_disabled_by_flag(api):
    client, app = api
    svc = service(lambda r: httpx.Response(200, json={}), AI_ENABLE_VOICE_TRANSCRIPTION="false")
    app.dependency_overrides[get_ai_service] = lambda: svc
    assert post(client).status_code == 501


# --- multiple Groq keys ------------------------------------------------------


def test_keys_parsed_from_both_variables_and_deduplicated():
    s = settings(GROQ_API_KEY="k1", GROQ_API_KEYS=" k2, k1 ,k3,, ")
    assert s.groq_api_keys == ("k1", "k2", "k3")
    assert s.public()["groq_key_count"] == 3


def test_rate_limited_key_fails_over_to_next_key():
    used = []

    def handler(req):
        key = req.headers["authorization"].split()[1]
        used.append(key)
        return httpx.Response(429) if key == "k1" else chat_ok("ok")

    svc = service(handler, GROQ_API_KEY="k1", GROQ_API_KEYS="k2", AI_ENABLE_FALLBACK="false")
    assert svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}]).text == "ok"
    svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}])
    assert used == ["k1", "k2", "k2"]  # k1 stays cooling down for later calls
    assert svc.sleeps == []  # type: ignore[attr-defined]  # failover spends no backoff


def test_rejected_key_is_dropped_and_other_key_used():
    used = []

    def handler(req):
        key = req.headers["authorization"].split()[1]
        used.append(key)
        return httpx.Response(401) if key == "bad" else chat_ok("ok")

    svc = service(handler, GROQ_API_KEY="bad", GROQ_API_KEYS="good")
    svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}])
    svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}])
    assert used == ["bad", "good", "good"]
    assert svc.status()["groq_keys"][0]["rejected"] is True


def test_per_key_call_budget_rotates_proactively():
    used = []

    def handler(req):
        used.append(req.headers["authorization"].split()[1])
        return chat_ok("ok")

    svc = service(handler, GROQ_API_KEY="k1", GROQ_API_KEYS="k2", GROQ_KEY_CALL_LIMIT="2")
    for _ in range(4):
        svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}])
    assert used == ["k1", "k1", "k2", "k2"]
    with pytest.raises(AIRateLimitError):  # both budgets spent
        svc.run_text(Task.INTENT, [{"role": "user", "content": "x"}])


def test_status_exposes_slots_not_key_material():
    svc = service(lambda r: chat_ok("ok"), GROQ_API_KEY="secretA", GROQ_API_KEYS="secretB")
    dumped = json.dumps(svc.status())
    assert "secretA" not in dumped and "secretB" not in dumped
    assert [k["slot"] for k in svc.status()["groq_keys"]] == [1, 2]
