"""Mask2Former panoptic segmentation, hosted on Hugging Face Inference (``hf-inference``).

Uses ``huggingface_hub.InferenceClient.image_segmentation`` against
``facebook/mask2former-swin-large-coco-panoptic``. The model runs on Hugging Face's servers: this process sends the
image bytes and parses the reply. Weights are never downloaded and no local framework is involved.

Output handling follows what the API actually returns: a list of segments, each with a ``label``, an optional
``score`` (panoptic models frequently omit it, and ``None`` is preserved rather than invented) and a ``mask`` that is a
base64-encoded black-and-white PNG. A result is not assumed to be a single binary mask.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx2
from huggingface_hub import InferenceClient
from huggingface_hub.errors import (
    HfHubHTTPError,
    InferenceTimeoutError,
    OverloadedError,
)
from PIL import Image, UnidentifiedImageError

from backend.ai.clients import MAX_BACKOFF_SECONDS, KeyPool, classify_status
from backend.ai.errors import (
    AIAuthError,
    AIConfigurationError,
    AIError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
)
from backend.ai.imaging import inspect_image

logger = logging.getLogger(__name__)

PROVIDER = "huggingface"
DEFAULT_PROVIDER = "hf-inference"
DEFAULT_MODEL = "facebook/mask2former-swin-large-coco-panoptic"


def map_hub_error(exc: Exception, model: str) -> AIError:
    """Translate a huggingface_hub / transport exception into a typed, secret-free ``AIError``."""
    kw = {"provider": PROVIDER, "model": model}
    if isinstance(exc, (InferenceTimeoutError, httpx2.TimeoutException)):
        return AITimeoutError("huggingface request timed out", **kw)
    if isinstance(exc, OverloadedError):
        return AIProviderUnavailableError("huggingface reports the model is overloaded", **kw)
    if isinstance(exc, HfHubHTTPError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return classify_status(status, PROVIDER, model)
        return AIProviderUnavailableError("huggingface returned an error", **kw)
    if isinstance(exc, httpx2.TransportError):
        return AIProviderUnavailableError("huggingface could not be reached", **kw)
    if isinstance(exc, ValueError) and "not supported" in str(exc).lower():
        return AIModelUnavailableError("the model is not supported by the configured provider", **kw)
    return AIInvalidResponseError("huggingface returned an unusable response", **kw)


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _decode_mask(encoded: str) -> tuple[Image.Image, str]:
    """Return the decoded mask image and a canonical PNG base64 string."""
    try:
        raw = base64.b64decode(encoded, validate=False)
        with Image.open(io.BytesIO(raw)) as src:
            mask = src.convert("L")
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError) as exc:
        raise AIInvalidResponseError("a returned mask is not a readable image", provider=PROVIDER) from exc
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return mask, base64.b64encode(buf.getvalue()).decode("ascii")


class Mask2FormerClient:
    def __init__(
        self,
        *,
        keys: Sequence[str] | KeyPool,
        model: str = DEFAULT_MODEL,
        provider: str = DEFAULT_PROVIDER,
        timeout: float = 60.0,
        max_retries: int = 2,
        max_image_bytes: int = 8 * 1024 * 1024,
        client_factory: Callable[[str], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not model.strip():
            raise AIConfigurationError("no segmentation model is configured", provider=PROVIDER)
        self.model = model.strip()
        self.provider = (provider or DEFAULT_PROVIDER).strip()
        self.keys = keys if isinstance(keys, KeyPool) else KeyPool(list(keys))
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.max_image_bytes = max_image_bytes
        self._factory = client_factory or self._default_factory
        self._clients: dict[str, Any] = {}
        self._sleep = sleep

    def _default_factory(self, key: str) -> InferenceClient:
        return InferenceClient(provider=self.provider, api_key=key, timeout=self.timeout)  # type: ignore[arg-type]

    def _client(self, key: str) -> Any:
        client = self._clients.get(key)
        if client is None:
            client = self._clients[key] = self._factory(key)
        return client

    def segment(self, image: bytes, content_type: str | None = None) -> dict[str, Any]:
        """Segment in-memory image bytes. For a local file, read it with ``backend.ai.imaging.read_image_file``."""
        info = inspect_image(image, self.max_image_bytes, declared_type=content_type)
        if not len(self.keys):
            raise AIConfigurationError("huggingface credentials are not configured", provider=PROVIDER, model=self.model)

        attempt = 0
        last_key_error: AIError | None = None
        while True:
            key = self.keys.acquire()
            if key is None:
                raise last_key_error or AIRateLimitError(
                    "huggingface: every configured API key is exhausted or cooling down", provider=PROVIDER, model=self.model)
            started = time.monotonic()
            try:
                output = self._client(key).image_segmentation(image, model=self.model)
                return self._parse(output, info.width, info.height)
            except AIError:
                raise
            except Exception as exc:  # noqa: BLE001 - mapped to a typed, secret-free error just below
                err = map_hub_error(exc, self.model)
            logger.warning("segmentation request failed: %s after %.1fs", err.code, time.monotonic() - started)
            if isinstance(err, AIRateLimitError):
                self.keys.rate_limited(key)
                last_key_error = err
                continue
            if isinstance(err, AIAuthError):
                self.keys.rejected(key)
                last_key_error = err
                continue
            if not err.retryable or attempt >= self.max_retries:
                raise err
            attempt += 1
            delay = min(MAX_BACKOFF_SECONDS, 0.5 * 2 ** (attempt - 1))
            self._sleep(delay + random.uniform(0, min(0.25, delay)))

    def _parse(self, output: Any, width: int, height: int) -> dict[str, Any]:
        if not isinstance(output, (list, tuple)):
            raise AIInvalidResponseError("segmentation returned an unexpected structure", provider=PROVIDER, model=self.model)
        segments: list[dict[str, Any]] = []
        for item in output:
            label, mask_b64, score = _field(item, "label"), _field(item, "mask"), _field(item, "score")
            if not isinstance(mask_b64, str) or not mask_b64:
                continue  # an element without a mask carries no segmentation data
            mask, png_b64 = _decode_mask(mask_b64)
            histogram = mask.histogram()
            covered = sum(histogram[1:])
            area = covered / (mask.width * mask.height)
            segments.append({
                "label": label if isinstance(label, str) else None,
                "score": float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None,
                "mask_png_base64": png_b64,
                "mask_width": mask.width,
                "mask_height": mask.height,
                "area_fraction": round(area, 6),
            })
        if not segments:
            raise AIInvalidResponseError("segmentation returned no masks", provider=PROVIDER, model=self.model)
        return {
            "provider": self.provider,
            "model": self.model,
            "image": {"width": width, "height": height},
            "masks": segments,
            "count": len(segments),
        }
