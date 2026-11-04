"""Unit tests for the hosted Mask2Former client.

The client is exercised with the library's real output types and real exceptions behind a fake
``InferenceClient``. No network is touched and no credits are used: these prove the client's behaviour, NOT that the
hosted API works (see ``test_live_hosted_ai.py`` for the opt-in live calls).
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import httpx2
import pytest
from huggingface_hub import InferenceClient
from huggingface_hub.errors import (
    HfHubHTTPError,
    InferenceTimeoutError,
    OverloadedError,
)
from huggingface_hub.inference._generated.types.image_segmentation import (
    ImageSegmentationOutputElement,
)
from PIL import Image

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
from backend.ai.imaging import read_image_file
from backend.ai.segmentation import DEFAULT_MODEL, DEFAULT_PROVIDER, Mask2FormerClient
from backend.ai.service import AIService
from backend.ai.settings import AISettings
from backend.ai.tests.hf_support import SECRET, mask_b64, png_bytes


def hub_error(status: int) -> HfHubHTTPError:
    request = httpx2.Request("POST", "https://router.huggingface.co/hf-inference/models/x")
    return HfHubHTTPError("boom", response=httpx2.Response(status, json={"error": "x"}, request=request))


class FakeHub:
    """Stands in for ``InferenceClient``: serves scripted outputs/exceptions and records every call."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def image_segmentation(self, image: Any, *, model: str | None = None, **kw: Any) -> Any:
        self.calls.append({"image_len": len(image), "model": model, **kw})
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step


def make(hub: FakeHub, keys: tuple[str, ...] = (SECRET,), **kw: Any) -> tuple[Mask2FormerClient, list[str]]:
    built: list[str] = []

    def factory(key: str) -> FakeHub:
        built.append(key)
        return hub

    kw.setdefault("sleep", lambda _s: None)
    return Mask2FormerClient(keys=keys, client_factory=factory, **kw), built


def elements() -> list[ImageSegmentationOutputElement]:
    return [
        ImageSegmentationOutputElement(label="person", mask=mask_b64(covered=(0, 0, 16, 12)), score=0.97),
        ImageSegmentationOutputElement(label="wall", mask=mask_b64(covered=(0, 12, 32, 24)), score=None),
    ]


# ---- output handling -----------------------------------------------------------------------------------------------
def test_every_segment_is_preserved_with_label_score_and_mask() -> None:
    hub = FakeHub(elements())
    client, _ = make(hub)
    out = client.segment(png_bytes((32, 24)), "image/png")
    assert hub.calls == [{"image_len": len(png_bytes((32, 24))), "model": "facebook/mask2former-swin-large-coco-panoptic"}]
    assert out["provider"] == "hf-inference" and out["model"] == DEFAULT_MODEL and out["count"] == 2
    assert out["image"] == {"width": 32, "height": 24}
    person, wall = out["masks"]
    assert (person["label"], person["score"]) == ("person", 0.97)
    assert (wall["label"], wall["score"]) == ("wall", None)  # a missing score stays None, never invented
    assert person["area_fraction"] == pytest.approx(16 * 12 / (32 * 24), abs=1e-3)
    assert (person["mask_width"], person["mask_height"]) == (32, 24)
    decoded = Image.open(io.BytesIO(base64.b64decode(person["mask_png_base64"])))
    assert decoded.format == "PNG" and decoded.size == (32, 24)  # a real, decodable mask image


def test_a_result_is_a_list_of_panoptic_segments_not_a_single_binary_mask() -> None:
    many = [ImageSegmentationOutputElement(label=f"obj{i}", mask=mask_b64(), score=0.5) for i in range(5)]
    out = make(FakeHub(many))[0].segment(png_bytes())
    assert out["count"] == 5 and [m["label"] for m in out["masks"]] == [f"obj{i}" for i in range(5)]


def test_dict_shaped_elements_are_accepted_too() -> None:
    out = make(FakeHub([{"label": "cat", "mask": mask_b64(), "score": 0.9}]))[0].segment(png_bytes())
    assert out["masks"][0]["label"] == "cat"


@pytest.mark.parametrize("output", [[], None, "not a list", {"label": "x"}, [{"label": "x"}], [{"label": "x", "mask": ""}]])
def test_empty_or_unexpected_output_is_an_error_not_a_fake_success(output: Any) -> None:
    hub = FakeHub(output)
    with pytest.raises(AIInvalidResponseError):
        make(hub)[0].segment(png_bytes())
    assert len(hub.calls) == 1  # a bad reply is not retried


def test_an_undecodable_mask_is_an_error() -> None:
    bad = [ImageSegmentationOutputElement(label="x", mask="@@@not-base64-image@@@", score=0.1)]
    with pytest.raises(AIInvalidResponseError, match="mask"):
        make(FakeHub(bad))[0].segment(png_bytes())


# ---- inputs -----------------------------------------------------------------------------------------------------------
def test_local_files_and_in_memory_bytes_are_both_supported(tmp_path: Path) -> None:
    path = tmp_path / "frame.png"
    path.write_bytes(png_bytes((40, 30)))
    hub = FakeHub(elements())
    client, _ = make(hub)
    data, info = read_image_file(path, 1_000_000)
    assert info.mime == "image/png" and (info.width, info.height) == (40, 30)
    assert client.segment(data, info.mime)["count"] == 2
    assert client.segment(png_bytes(), "image/png")["count"] == 2
    assert all(isinstance(c["image_len"], int) for c in hub.calls)  # bytes were sent, never the path


def test_inputs_are_validated_before_any_request() -> None:
    hub = FakeHub(elements())
    client, _ = make(hub, max_image_bytes=1000)
    with pytest.raises(AIInvalidInputError, match="empty"):
        client.segment(b"")
    with pytest.raises(AIInvalidInputError, match="readable image"):
        client.segment(b"definitely not an image")
    with pytest.raises(AIInvalidInputError, match="does not match"):
        client.segment(png_bytes(), "image/jpeg")
    with pytest.raises(AIPayloadTooLargeError):
        client.segment(png_bytes((300, 300)) + b"\x00" * 2000)
    assert hub.calls == []


# ---- errors, retries and key failover --------------------------------------------------------------------------------
def test_authentication_failure_fails_over_then_stops() -> None:
    hub = FakeHub(hub_error(401), elements())
    client, built = make(hub, keys=("hf_one", "hf_two"))
    assert client.segment(png_bytes())["count"] == 2
    assert built == ["hf_one", "hf_two"]

    only = FakeHub(hub_error(403))
    with pytest.raises(AIAuthError):
        make(only)[0].segment(png_bytes())
    assert len(only.calls) == 1


def test_rate_limits_try_each_key_once_without_hammering() -> None:
    hub = FakeHub(hub_error(429))
    with pytest.raises(AIRateLimitError):
        make(hub, keys=("hf_a", "hf_b"))[0].segment(png_bytes())
    assert len(hub.calls) == 2


def test_unavailable_model_and_bad_requests_are_permanent() -> None:
    for error, expected in ((hub_error(404), AIModelUnavailableError), (hub_error(400), AIInvalidInputError),
                            (ValueError("Model x is not supported by provider y"), AIModelUnavailableError)):
        hub = FakeHub(error)
        with pytest.raises(expected):
            make(hub)[0].segment(png_bytes())
        assert len(hub.calls) == 1


def test_transient_failures_are_retried_a_bounded_number_of_times() -> None:
    hub = FakeHub(hub_error(503), OverloadedError("busy"), elements())
    assert make(hub, max_retries=2)[0].segment(png_bytes())["count"] == 2
    assert len(hub.calls) == 3

    always = FakeHub(hub_error(500))
    with pytest.raises(AIProviderUnavailableError):
        make(always, max_retries=2)[0].segment(png_bytes())
    assert len(always.calls) == 3


def test_timeouts_and_connection_failures_are_typed() -> None:
    hub = FakeHub(InferenceTimeoutError("slow"))
    with pytest.raises(AITimeoutError):
        make(hub, max_retries=1)[0].segment(png_bytes())
    assert len(hub.calls) == 2
    request = httpx2.Request("POST", "https://router.huggingface.co/x")
    with pytest.raises(AIProviderUnavailableError):
        make(FakeHub(httpx2.ConnectError("no route", request=request)), max_retries=0)[0].segment(png_bytes())


def test_the_real_inference_client_is_configured_for_hf_inference_with_a_timeout() -> None:
    client = Mask2FormerClient(keys=("hf_k",), timeout=9.0)
    sdk = client._client("hf_k")
    assert isinstance(sdk, InferenceClient) and sdk.timeout == 9.0
    assert client.provider == "hf-inference" and DEFAULT_PROVIDER == "hf-inference"
    assert client._client("hf_k") is sdk  # reused, not rebuilt


def test_missing_credentials_or_model_is_a_configuration_error() -> None:
    hub = FakeHub(elements())
    with pytest.raises(AIConfigurationError):
        make(hub, keys=())[0].segment(png_bytes())
    with pytest.raises(AIConfigurationError):
        Mask2FormerClient(keys=("k",), model=" ")
    assert hub.calls == []


def test_credentials_and_image_data_never_appear_in_errors_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    image = png_bytes()
    b64 = base64.b64encode(image).decode()
    for error in (hub_error(401), hub_error(500), ValueError(f"leaky {SECRET}")):
        with pytest.raises(Exception) as info:
            make(FakeHub(error), max_retries=0)[0].segment(image)
        text = f"{info.value!s}{info.value!r}"
        assert SECRET not in text and b64[:40] not in text
    assert all(SECRET not in r.getMessage() and b64[:40] not in r.getMessage() for r in caplog.records)


# ---- AIService integration -----------------------------------------------------------------------------------------
def settings(**env: str) -> AISettings:
    base = {"GROQ_API_KEY": "gsk_unused", "HF_TOKEN": SECRET, "HF_SEGMENTATION_MODEL": DEFAULT_MODEL,
            "HF_INFERENCE_PROVIDER": "hf-inference", "AI_MAX_RETRIES": "0"}
    return AISettings.from_env({**base, **env})


def test_the_service_routes_segmentation_through_the_shared_mask2former_client() -> None:
    service = AIService(settings())
    shared, _ = make(FakeHub(elements()))
    service._segmenter = shared
    assert service.segmentation_client() is shared
    result = service.segment_image(png_bytes(), "image/png")
    assert result["task"] == "visual_segmentation" and result["model"] == DEFAULT_MODEL
    assert result["inference_provider"] == "hf-inference" and result["count"] == 2
    assert [m["label"] for m in result["masks"]] == ["person", "wall"]


def test_the_provider_comes_from_configuration_and_defaults_to_hf_inference() -> None:
    assert AIService(settings()).segmentation_client().provider == "hf-inference"
    assert AIService(settings(HF_INFERENCE_PROVIDER="")).segmentation_client().provider == "hf-inference"


def test_without_a_segmentation_model_the_capability_is_disabled() -> None:
    service = AIService(settings(HF_SEGMENTATION_MODEL=""))
    with pytest.raises(AIUnsupportedTaskError, match="unavailable"):
        service.segment_image(png_bytes(), "image/png")
    assert service.status()["tasks"]["visual_segmentation"]["state"] == "disabled"


def test_a_dedicated_endpoint_keeps_using_the_existing_endpoint_path() -> None:
    service = AIService(settings(HF_SEGMENTATION_ENDPOINT="https://example.endpoints.huggingface.cloud"))
    spec = service.registry[next(t for t in service.registry if t.value == "visual_segmentation")]
    assert spec.endpoint == "https://example.endpoints.huggingface.cloud" and spec.enabled
