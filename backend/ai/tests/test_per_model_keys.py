"""Each hosted model has its own API-key variable; the right one is what the request actually carries."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from backend.ai import clients as clients_module
from backend.ai.registry import Task, build_registry
from backend.ai.service import AIService
from backend.ai.settings import TASK_KEY_ENV_VARS, AISettings

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
EXPECTED = {
    Task.INTENT: "GROQ_INTENT_API_KEY",
    Task.REQUIREMENTS: "GROQ_REQUIREMENTS_API_KEY",
    Task.ROOT_CAUSE: "GROQ_ROOT_CAUSE_API_KEY",
    Task.INVESTIGATION: "GROQ_INVESTIGATION_API_KEY",
    Task.TRANSCRIPTION: "GROQ_TRANSCRIPTION_API_KEY",
}


def settings(**env: str) -> AISettings:
    return AISettings.from_env({"GROQ_API_KEY": "gsk_shared", "HF_TOKEN": "hf_shared", **env})


@pytest.fixture()
def wire(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Intercept every real client's HTTP call (the real per-task client construction still runs)."""
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "auth": request.headers["authorization"]})
        if request.url.path.endswith("/audio/transcriptions"):
            return httpx.Response(200, json={"text": "hello", "language": "en", "duration": 1.0})
        return httpx.Response(200, json={"id": "r", "model": "m", "choices": [{"message": {"content": "{}"}}]})

    real = httpx.Client

    def patched(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(clients_module.httpx, "Client", patched)
    return seen


def test_every_task_maps_to_its_own_variable() -> None:
    reg = build_registry(settings())
    for task, var in EXPECTED.items():
        assert reg[task].key_env == var
    assert reg[Task.VISION].key_env == "HF_VISION_API_KEY"
    assert build_registry(settings(VISION_PROVIDER="groq"))[Task.VISION].key_env == "GROQ_VISION_API_KEY"
    assert reg[Task.SEGMENTATION].key_env == "HF_SEGMENTATION_API_KEY"
    assert {s.key_env for s in reg.values()} <= set(TASK_KEY_ENV_VARS)


def test_template_and_example_declare_every_variable() -> None:
    example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    for var in TASK_KEY_ENV_VARS:
        assert f"{var}=REPLACE_WITH_{var}" in example


def test_unfilled_placeholders_count_as_not_configured() -> None:
    s = AISettings.from_env({
        "GROQ_API_KEY": "REPLACE_WITH_GROQ_API_KEY", "HF_TOKEN": "REPLACE_WITH_HF_TOKEN",
        "GROQ_API_KEYS": "REPLACE_WITH_X, gsk_real",
        "GROQ_INTENT_API_KEY": "REPLACE_WITH_GROQ_INTENT_API_KEY", "GROQ_REQUIREMENTS_API_KEY": "gsk_req"})
    assert s.groq_api_keys == ("gsk_real",) and s.hf_token == ""
    assert s.dedicated_keys == {"GROQ_REQUIREMENTS_API_KEY": "gsk_req"}


def test_dedicated_key_is_used_first_then_shared_and_status_hides_keys() -> None:
    ai = AIService(settings(GROQ_INTENT_API_KEY="gsk_intent"))
    intent, reqs = ai.registry[Task.INTENT], ai.registry[Task.REQUIREMENTS]
    assert ai._keys_for(intent) == ("gsk_intent", "gsk_shared")
    assert ai._keys_for(reqs) == ("gsk_shared",)
    status = ai.status()
    assert status["tasks"][Task.INTENT.value]["api_key_source"] == "dedicated"
    assert status["tasks"][Task.INTENT.value]["api_key_variable"] == "GROQ_INTENT_API_KEY"
    assert status["tasks"][Task.REQUIREMENTS.value]["api_key_source"] == "shared"
    flat = str(status)
    assert "gsk_intent" not in flat and "gsk_shared" not in flat and "hf_shared" not in flat
    assert status["config"]["dedicated_key_variables_set"] == ["GROQ_INTENT_API_KEY"]
    assert "gsk_intent" not in repr(ai.settings)


def test_only_a_dedicated_key_is_enough_without_any_shared_key() -> None:
    ai = AIService(AISettings.from_env({"GROQ_INTENT_API_KEY": "gsk_only_intent"}))
    states = {k: v["state"] for k, v in ai.status()["tasks"].items()}
    assert states[Task.INTENT.value] == "configured" and states[Task.REQUIREMENTS.value] == "unconfigured"


def test_requests_carry_the_key_of_the_model_that_made_them(wire: list[dict[str, str]]) -> None:
    ai = AIService(settings(
        GROQ_INTENT_API_KEY="gsk_intent", GROQ_REQUIREMENTS_API_KEY="gsk_requirements",
        GROQ_TRANSCRIPTION_API_KEY="gsk_voice"))
    msgs = [{"role": "user", "content": "hi"}]
    ai.run_text(Task.INTENT, msgs)
    ai.run_text(Task.REQUIREMENTS, msgs)
    ai.run_text(Task.ROOT_CAUSE, msgs)  # no dedicated key: shared
    ai.transcribe("a.webm", WEBM, "audio/webm")
    assert [w["auth"] for w in wire] == [
        "Bearer gsk_intent", "Bearer gsk_requirements", "Bearer gsk_shared", "Bearer gsk_voice"]


def test_failed_dedicated_key_fails_over_to_the_shared_key(monkeypatch: pytest.MonkeyPatch) -> None:
    wire: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        wire.append({"url": str(request.url), "auth": request.headers["authorization"]})
        if request.headers["authorization"] == "Bearer gsk_bad":
            return httpx.Response(401, json={"error": "invalid"})
        return httpx.Response(200, json={"id": "r", "model": "m", "choices": [{"message": {"content": "{}"}}]})

    real = httpx.Client
    monkeypatch.setattr(clients_module.httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    ai = AIService(settings(GROQ_INTENT_API_KEY="gsk_bad"))
    out = ai.run_text(Task.INTENT, [{"role": "user", "content": "hi"}])
    assert out.text == "{}" and [w["auth"] for w in wire] == ["Bearer gsk_bad", "Bearer gsk_shared"]
