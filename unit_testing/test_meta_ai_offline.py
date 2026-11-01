"""Meta Model API adapter tests — offline via ``httpx.MockTransport``.

No socket is opened.  The mock transport also lets the tests assert the exact
request shape: one bearer header, a single ``/chat/completions`` suffix, and
structured JSON on the wire.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from backend.verification.llm.meta_ai import (
    MetaAIConfigurationError,
    MetaAIProviderDirect,
    MetaAIResponseFormatError,
    MetaAPIAuthError,
    MetaAPIServerError,
    get_meta_ai_provider,
)

BASE_URL = "https://api.example.test/v1"


def _chat_response(
    content: str, *, response_id: str | None = "resp_1"
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "muse-spark-1.3",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    if response_id is not None:
        payload["id"] = response_id
    return payload


def _provider(
    transport: httpx.MockTransport,
    *,
    max_attempts: int = 3,
    sleeps: list[float] | None = None,
    endpoint: str = "/chat/completions",
    base_url: str = BASE_URL,
) -> MetaAIProviderDirect:
    recorded = sleeps if sleeps is not None else []
    return MetaAIProviderDirect(
        base_url=base_url,
        api_key="test-key",
        endpoint=endpoint,
        max_attempts=max_attempts,
        transport=transport,
        sleep=recorded.append,
    )


def test_missing_credentials_raise_instead_of_sending_an_anonymous_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("META_AI_API_KEY", raising=False)
    monkeypatch.delenv("META_API", raising=False)

    with pytest.raises(MetaAIConfigurationError):
        MetaAIProviderDirect(base_url=BASE_URL)
    with pytest.raises(MetaAIConfigurationError):
        get_meta_ai_provider(base_url=BASE_URL, use_langchain=False)


def test_empty_credentials_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_AI_API_KEY", "   ")

    with pytest.raises(MetaAIConfigurationError):
        MetaAIProviderDirect(base_url=BASE_URL, api_key="")


def test_endpoint_is_resolved_once_and_bearer_header_is_single() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_chat_response('{"ok": true}'))

    provider = _provider(
        httpx.MockTransport(handler),
        endpoint="chat/completions",
        base_url=BASE_URL + "/",
    )
    try:
        provider.invoke("muse-spark-1.3", [{"role": "user", "content": "hi"}])
    finally:
        provider.close()

    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == BASE_URL + "/chat/completions"
    assert request.headers.get("authorization") == "Bearer test-key"
    assert request.headers.get_list("authorization") == ["Bearer test-key"]


def test_usage_is_read_not_popped_and_request_id_is_not_invented() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_chat_response('{"ok": true}', response_id=None)
        )

    provider = _provider(httpx.MockTransport(handler))
    try:
        raw, usage = provider.invoke(
            "muse-spark-1.3", [{"role": "user", "content": "hi"}]
        )
        payload = provider.investigate(
            {"prompt": "analyse this evidence", "prompt_version": "v-test"}
        )
    finally:
        provider.close()

    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert raw["usage"] == usage  # the raw payload was not mutated
    metadata = payload["_metadata"]
    assert metadata["request_id"] is None
    assert metadata["provider"] == "meta_ai"
    assert metadata["model"] == "muse-spark-1.3"
    assert metadata["prompt_version"] == "v-test"


def test_rate_limit_is_retried_with_bounded_backoff() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, json=_chat_response('{"ok": true}'))

    sleeps: list[float] = []
    provider = _provider(httpx.MockTransport(handler), sleeps=sleeps)
    try:
        raw, _ = provider.invoke("muse-spark-1.3", [{"role": "user", "content": "hi"}])
    finally:
        provider.close()

    assert calls["count"] == 2
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 8.0
    assert raw["choices"][0]["message"]["content"] == '{"ok": true}'


def test_retries_are_bounded_and_stop_on_exhaustion() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"error": "unavailable"})

    sleeps: list[float] = []
    provider = _provider(httpx.MockTransport(handler), max_attempts=3, sleeps=sleeps)
    try:
        with pytest.raises(MetaAPIServerError):
            provider.invoke("muse-spark-1.3", [{"role": "user", "content": "hi"}])
    finally:
        provider.close()

    assert calls["count"] == 3
    assert len(sleeps) == 2


def test_auth_errors_are_not_retried() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(401, json={"error": "invalid key"})

    provider = _provider(httpx.MockTransport(handler))
    try:
        with pytest.raises(MetaAPIAuthError):
            provider.invoke("muse-spark-1.3", [{"role": "user", "content": "hi"}])
    finally:
        provider.close()

    assert calls["count"] == 1


def test_invalid_json_from_the_model_is_a_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response("this is not json"))

    provider = _provider(httpx.MockTransport(handler))
    try:
        with pytest.raises(MetaAIResponseFormatError):
            provider.investigate({"prompt": "analyse this evidence"})
    finally:
        provider.close()


def test_tool_use_is_disabled_and_only_the_investigation_prompt_is_sent() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_chat_response(json.dumps({"summary": "ok"})))

    provider = _provider(httpx.MockTransport(handler))
    try:
        provider.investigate({"prompt": "EVIDENCE: evt_1"})
    finally:
        provider.close()

    assert len(bodies) == 1
    body = bodies[0]
    assert body["temperature"] == 0.0
    assert body["response_format"] == {"type": "json_object"}
    assert "tools" not in body
    assert body["messages"][0]["role"] == "system"
    assert "untrusted" in body["messages"][0]["content"].lower()
    assert body["messages"][1] == {"role": "user", "content": "EVIDENCE: evt_1"}
