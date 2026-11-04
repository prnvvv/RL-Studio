"""Unit tests for the hosted Qwen vision client.

The real OpenAI SDK runs against an in-process scripted HTTP transport, so request building and error classes are the
genuine ones. No network is touched and no credits are used: these tests prove the client's behaviour, NOT that the
hosted API works (see ``test_live_hosted_ai.py`` for the opt-in live calls).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx2
import openai
import pytest

from backend.ai.errors import (
    AIAuthError,
    AIConfigurationError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIPayloadTooLargeError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
    AIUnsupportedTaskError,
)
from backend.ai.service import AIService
from backend.ai.settings import AISettings
from backend.ai.tests.hf_support import SECRET, png_bytes
from backend.ai.vision import DEFAULT_BASE_URL, DEFAULT_MODEL, QwenVisionClient

OK_BODY = {
    "id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": DEFAULT_MODEL,
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "A red square."}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
}


class Server:
    """Scripted transport: a list of responses (or exceptions) served in order; every request is recorded."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        status, body = step
        return httpx2.Response(status, json=body, request=request)

    def body(self, i: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[i].content)

    def auth(self, i: int = 0) -> str:
        return self.requests[i].headers["authorization"]


def make(server: Server, keys: tuple[str, ...] = (SECRET,), **kw: Any) -> tuple[QwenVisionClient, list[str]]:
    built: list[str] = []

    def factory(key: str) -> openai.OpenAI:
        built.append(key)
        return openai.OpenAI(base_url=DEFAULT_BASE_URL, api_key=key, max_retries=0,
                             http_client=httpx2.Client(transport=httpx2.MockTransport(server)))

    kw.setdefault("sleep", lambda _s: None)
    return QwenVisionClient(keys=keys, client_factory=factory, **kw), built


def ok() -> tuple[int, dict[str, Any]]:
    return 200, OK_BODY


# ---- request shape ----------------------------------------------------------------------------------------------
def test_sends_the_exact_model_id_prompt_and_image_as_a_data_url() -> None:
    server = Server(ok())
    client, _ = make(server)
    out = client.describe("What colour is the square?", image=png_bytes())
    body = server.body()
    assert body["model"] == "Qwen/Qwen2.5-VL-3B-Instruct:featherless-ai"
    parts = body["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "What colour is the square?"}
    assert parts[1]["type"] == "image_url" and parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert str(server.requests[0].url) == "https://router.huggingface.co/v1/chat/completions"
    assert server.auth() == f"Bearer {SECRET}"
    assert (out["text"], out["model"], out["request_id"]) == ("A red square.", DEFAULT_MODEL, "chatcmpl-test")
    assert out["usage"]["total_tokens"] == 14


def test_the_prompt_is_configurable_not_hardcoded() -> None:
    server = Server(ok())
    client, _ = make(server)
    client.describe("Is there an obstacle on the left?", image=png_bytes())
    client.describe(image=png_bytes())  # the documented default
    assert server.body(0)["messages"][0]["content"][0]["text"] == "Is there an obstacle on the left?"
    assert server.body(1)["messages"][0]["content"][0]["text"] == "Describe this image in one sentence."


def test_a_local_file_is_sent_as_bytes_and_its_path_never_leaves_the_process(tmp_path: Path) -> None:
    path = tmp_path / "secret_dir_name" / "frame.png"
    path.parent.mkdir()
    path.write_bytes(png_bytes())
    server = Server(ok())
    client, _ = make(server)
    client.describe("Describe.", image_path=path)
    raw = server.requests[0].content.decode()
    assert "data:image/png;base64," in raw
    assert "secret_dir_name" not in raw and "frame.png" not in raw and str(tmp_path) not in raw


def test_an_https_url_is_passed_through_for_the_provider_to_fetch() -> None:
    server = Server(ok())
    client, _ = make(server)
    client.describe("Describe.", image_url="https://example.com/a/b.jpg")
    assert server.body()["messages"][0]["content"][1]["image_url"]["url"] == "https://example.com/a/b.jpg"


@pytest.mark.parametrize("url", [
    "http://example.com/a.png", "file:///etc/passwd", "https://localhost/a.png", "https://127.0.0.1/a.png",
    "https://user:pw@example.com/a.png", "https://192.168.1.5/a.png", "", "https:///a.png",
])
def test_unsafe_image_urls_are_rejected_before_any_request(url: str) -> None:
    server = Server(ok())
    client, _ = make(server)
    with pytest.raises(AIInvalidInputError):
        client.describe("Describe.", image_url=url)
    assert server.requests == []


# ---- input validation ----------------------------------------------------------------------------------------------
def test_inputs_are_validated_before_any_request() -> None:
    server = Server(ok())
    client, _ = make(server, max_image_bytes=1000)
    good = png_bytes()
    with pytest.raises(AIInvalidInputError, match="prompt is empty"):
        client.describe("   ", image=good)
    with pytest.raises(AIInvalidInputError, match="exactly one"):
        client.describe("x")
    with pytest.raises(AIInvalidInputError, match="exactly one"):
        client.describe("x", image=good, image_url="https://example.com/a.png")
    with pytest.raises(AIInvalidInputError, match="empty"):
        client.describe("x", image=b"")
    with pytest.raises(AIInvalidInputError, match="readable image"):
        client.describe("x", image=b"this is not an image at all")
    with pytest.raises(AIInvalidInputError, match="does not match"):
        client.describe("x", image=good, content_type="image/jpeg")
    with pytest.raises(AIPayloadTooLargeError):
        client.describe("x", image=good + b"\x00" * 2000)
    with pytest.raises(AIInvalidInputError, match="prompt exceeds"):
        client.describe("x" * 9000, image=good)
    with pytest.raises(AIInvalidInputError):
        client.describe("x", image_path="/definitely/not/here.png")
    assert server.requests == []


def test_a_decompression_bomb_sized_image_is_refused() -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("1", (6000, 6000)).save(buf, format="PNG")  # 36 Mpx, tiny on the wire
    server = Server(ok())
    client, _ = make(server)
    with pytest.raises(AIInvalidInputError, match="dimensions"):
        client.describe("x", image=buf.getvalue())
    assert server.requests == []


# ---- response handling --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("body", [
    {**OK_BODY, "choices": []},
    {**OK_BODY, "choices": [{"index": 0, "message": {"role": "assistant", "content": "   "}}]},
    {**OK_BODY, "choices": [{"index": 0, "message": {"role": "assistant", "content": None}}]},
])
def test_malformed_or_empty_responses_are_explicit_errors(body: dict[str, Any]) -> None:
    server = Server((200, body))
    client, _ = make(server)
    with pytest.raises(AIInvalidResponseError):
        client.describe("x", image=png_bytes())
    assert len(server.requests) == 1  # a bad reply is not retried


# ---- errors, retries and key failover -------------------------------------------------------------------------------
def test_a_rejected_key_fails_over_to_the_next_key_and_is_never_retried_blindly() -> None:
    server = Server((401, {"error": "bad key"}), ok())
    client, built = make(server, keys=("hf_first_key", "hf_second_key"))
    assert client.describe("x", image=png_bytes())["text"] == "A red square."
    assert [r.headers["authorization"] for r in server.requests] == ["Bearer hf_first_key", "Bearer hf_second_key"]
    assert built == ["hf_first_key", "hf_second_key"]
    client.describe("x", image=png_bytes())
    assert server.requests[-1].headers["authorization"] == "Bearer hf_second_key"  # the dead key is not tried again


def test_authentication_failure_with_no_other_key_is_not_retried() -> None:
    server = Server((401, {"error": "bad key"}))
    client, _ = make(server)
    with pytest.raises(AIAuthError):
        client.describe("x", image=png_bytes())
    assert len(server.requests) == 1


def test_rate_limit_moves_to_the_next_key_then_stops_without_hammering() -> None:
    server = Server((429, {"error": "slow"}))
    client, _ = make(server, keys=("hf_a", "hf_b"))
    with pytest.raises(AIRateLimitError):
        client.describe("x", image=png_bytes())
    assert len(server.requests) == 2  # one attempt per key, then give up


def test_unavailable_model_and_invalid_requests_are_permanent_not_retried() -> None:
    for status, exc in ((404, AIModelUnavailableError), (400, AIInvalidInputError), (422, AIInvalidInputError)):
        server = Server((status, {"error": "x"}))
        client, _ = make(server)
        with pytest.raises(exc):
            client.describe("x", image=png_bytes())
        assert len(server.requests) == 1


def test_transient_provider_errors_are_retried_a_bounded_number_of_times() -> None:
    server = Server((503, {"error": "busy"}), (503, {"error": "busy"}), ok())
    client, _ = make(server, max_retries=2)
    assert client.describe("x", image=png_bytes())["text"] == "A red square."
    assert len(server.requests) == 3

    server = Server((500, {"error": "down"}))
    client, _ = make(server, max_retries=2)
    with pytest.raises(AIProviderUnavailableError):
        client.describe("x", image=png_bytes())
    assert len(server.requests) == 3  # 1 + 2 retries, then stop


def test_timeouts_and_connection_failures_are_typed_and_bounded() -> None:
    req = httpx2.Request("POST", "https://router.huggingface.co/v1/chat/completions")
    server = Server(httpx2.ReadTimeout("slow", request=req))
    client, _ = make(server, max_retries=1)
    with pytest.raises(AITimeoutError):
        client.describe("x", image=png_bytes())
    assert len(server.requests) == 2

    server = Server(httpx2.ConnectError("no route", request=req))
    client, _ = make(server, max_retries=0)
    with pytest.raises(AIProviderUnavailableError):
        client.describe("x", image=png_bytes())


def test_request_timeout_is_applied_to_the_sdk_client() -> None:
    client = QwenVisionClient(keys=("hf_k",), timeout=7.5)
    sdk = client._client("hf_k")
    assert sdk.timeout == 7.5 and sdk.max_retries == 0


def test_sdk_clients_are_reused_not_rebuilt_per_request() -> None:
    server = Server(ok())
    client, built = make(server)
    for _ in range(3):
        client.describe("x", image=png_bytes())
    assert built == [SECRET]


def test_missing_credentials_or_model_is_a_configuration_error_without_a_request() -> None:
    server = Server(ok())
    client, _ = make(server, keys=())
    with pytest.raises(AIConfigurationError):
        client.describe("x", image=png_bytes())
    with pytest.raises(AIConfigurationError):
        QwenVisionClient(keys=("k",), model="  ")
    assert server.requests == []


# ---- secrecy ----------------------------------------------------------------------------------------------------------
def test_credentials_prompts_and_image_data_never_appear_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    prompt = "CONFIDENTIAL-PROMPT-TEXT"
    image = png_bytes()
    import base64

    b64 = base64.b64encode(image).decode()
    caplog.set_level(logging.DEBUG)
    for step in ((401, {"error": f"{SECRET} {prompt}"}), (500, {"error": f"{SECRET}"}), (429, {"error": "x"})):
        server = Server(step)
        client, _ = make(server, max_retries=0)
        with pytest.raises(Exception) as info:
            client.describe(prompt, image=image)
        text = f"{info.value!s}{info.value!r}"
        for forbidden in (SECRET, prompt, b64[:40]):
            assert forbidden not in text
    for record in caplog.records:
        message = record.getMessage()
        assert SECRET not in message and prompt not in message and b64[:40] not in message


# ---- AIService integration -----------------------------------------------------------------------------------------
def settings(**env: str) -> AISettings:
    base = {"GROQ_API_KEY": "gsk_unused", "HF_TOKEN": SECRET, "VISION_PROVIDER": "huggingface",
            "VISION_MODEL": DEFAULT_MODEL, "AI_MAX_RETRIES": "0"}
    return AISettings.from_env({**base, **env})


def test_the_service_routes_visual_investigation_through_the_shared_qwen_client() -> None:
    service = AIService(settings())
    server = Server(ok())
    shared, _ = make(server)
    service._vision = shared  # the one reusable client the service hands out
    assert service.vision_client() is shared
    result = service.analyze_image("What is in the scene?", png_bytes(), "image/png")
    assert result.text == "A red square." and result.provider == "huggingface" and result.model == DEFAULT_MODEL
    assert result.task == "visual_investigation" and result.fallback_used is False
    assert server.auth() == f"Bearer {SECRET}"


def test_the_dedicated_vision_key_is_tried_first_then_the_shared_token() -> None:
    service = AIService(settings(HF_VISION_API_KEY="hf_dedicated_key"))
    client = service.vision_client()
    assert list(client.keys._keys) == ["hf_dedicated_key", SECRET]
    assert service.key_source(service.registry[next(t for t in service.registry if t.value == "visual_investigation")]) == "dedicated"


def test_without_a_vision_model_the_capability_is_disabled_and_nothing_else_is_substituted() -> None:
    service = AIService(settings(VISION_MODEL=""))
    with pytest.raises(AIUnsupportedTaskError, match="unavailable"):
        service.analyze_image("x", png_bytes(), "image/png")
    state = service.status()["tasks"]["visual_investigation"]
    assert state["state"] == "disabled" and state["model"] is None
