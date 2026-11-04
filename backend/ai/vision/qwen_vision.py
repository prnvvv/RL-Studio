"""Qwen2.5-VL visual understanding, hosted on Hugging Face Inference Providers (Featherless AI).

A thin, reusable client over the OpenAI-compatible Hugging Face router (``https://router.huggingface.co/v1``) using
the OpenAI Python SDK. Nothing runs locally: this process prepares the image, sends one HTTPS request, and parses the
reply. There is no local-inference fallback. The model id carries the provider suffix
(``Qwen/Qwen2.5-VL-3B-Instruct:featherless-ai``) exactly as the router expects it.

Failures are typed (``backend.ai.errors``) and never contain credentials, prompts or image data. Key failover and
bounded retries mirror the rest of the AI layer: a rejected or rate-limited key moves to the next configured key;
only transient errors (timeouts, provider 5xx) are retried, with backoff and a hard cap.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

import openai

from backend.ai.clients import MAX_BACKOFF_SECONDS, KeyPool
from backend.ai.errors import (
    AIAuthError,
    AIConfigurationError,
    AIError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIPayloadTooLargeError,
    AIProviderUnavailableError,
    AIQuotaError,
    AIRateLimitError,
    AITimeoutError,
)
from backend.ai.imaging import (
    inspect_image,
    read_image_file,
    to_data_url,
    validate_image_url,
)

logger = logging.getLogger(__name__)

PROVIDER = "huggingface"
DEFAULT_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-VL-3B-Instruct:featherless-ai"
MAX_PROMPT_CHARS = 8000
DEFAULT_PROMPT = "Describe this image in one sentence."


def map_openai_error(exc: Exception, model: str) -> AIError:
    """Translate an OpenAI-SDK exception into a typed, secret-free ``AIError``."""
    kw = {"provider": PROVIDER, "model": model}
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return AIAuthError("huggingface rejected the configured credentials", **kw)
    if isinstance(exc, openai.RateLimitError):
        return AIRateLimitError("huggingface rate limit or quota reached", **kw)
    if isinstance(exc, openai.NotFoundError):
        return AIModelUnavailableError("huggingface reports the model or provider is unavailable", **kw)
    if isinstance(exc, openai.APITimeoutError):
        return AITimeoutError("huggingface request timed out", **kw)
    if isinstance(exc, openai.APIConnectionError):
        return AIProviderUnavailableError("huggingface could not be reached", **kw)
    if isinstance(exc, (openai.BadRequestError, openai.UnprocessableEntityError)):
        return AIInvalidInputError("huggingface rejected the request as invalid", **kw)
    if isinstance(exc, openai.APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        if status == 402:
            return AIQuotaError("huggingface reports that credits or quota are exhausted (HTTP 402)", **kw)
        if status == 413:
            return AIPayloadTooLargeError("huggingface rejected the payload as too large", **kw)
        if status >= 500:
            return AIProviderUnavailableError(f"huggingface is unavailable (HTTP {status})", **kw)
        return AIInvalidResponseError(f"huggingface returned unexpected HTTP {status}", **kw)
    return AIInvalidResponseError("huggingface returned an unusable response", **kw)


class QwenVisionClient:
    """Reusable hosted vision client: one SDK client per credential, created lazily and reused."""

    def __init__(
        self,
        *,
        keys: Sequence[str] | KeyPool,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        max_retries: int = 2,
        max_image_bytes: int = 8 * 1024 * 1024,
        client_factory: Callable[[str], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not model.strip():
            raise AIConfigurationError("no vision model is configured", provider=PROVIDER)
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.keys = keys if isinstance(keys, KeyPool) else KeyPool(list(keys))
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.max_image_bytes = max_image_bytes
        self._factory = client_factory or self._default_factory
        self._clients: dict[str, Any] = {}
        self._sleep = sleep

    def _default_factory(self, key: str) -> openai.OpenAI:
        # max_retries=0: retry policy is ours (bounded, transient-only), not the SDK's.
        return openai.OpenAI(base_url=self.base_url, api_key=key, timeout=self.timeout, max_retries=0)

    def _client(self, key: str) -> Any:
        client = self._clients.get(key)
        if client is None:
            client = self._clients[key] = self._factory(key)
        return client

    # ---- inputs ---------------------------------------------------------------------------------------------
    def _content(self, prompt: str, image: bytes | None, image_url: str | None, image_path: Any, content_type: str | None) -> list[dict[str, Any]]:
        text = (prompt or "").strip()
        if not text:
            raise AIInvalidInputError("the prompt is empty")
        if len(text) > MAX_PROMPT_CHARS:
            raise AIInvalidInputError(f"the prompt exceeds {MAX_PROMPT_CHARS} characters")
        sources = [s for s in (image, image_url, image_path) if s is not None]
        if len(sources) != 1:
            raise AIInvalidInputError("provide exactly one of image bytes, an https image URL, or a local image path")
        if image_url is not None:
            url = validate_image_url(image_url)
        else:
            if image_path is not None:
                image, info = read_image_file(image_path, self.max_image_bytes)
            else:
                info = inspect_image(image or b"", self.max_image_bytes, declared_type=content_type)
            url = to_data_url(image or b"", info.mime)  # the provider sees bytes, never a filesystem path
        return [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]

    # ---- call -----------------------------------------------------------------------------------------------
    def describe(
        self,
        prompt: str = DEFAULT_PROMPT,
        *,
        image: bytes | None = None,
        image_url: str | None = None,
        image_path: Any = None,
        content_type: str | None = None,
        max_tokens: int | None = 1024,
    ) -> dict[str, Any]:
        """Ask the hosted model about one image. Returns ``text``, ``model``, ``request_id`` and ``usage``."""
        content = self._content(prompt, image, image_url, image_path, content_type)
        messages = [{"role": "user", "content": content}]
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
                kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
                if max_tokens:
                    kwargs["max_tokens"] = max_tokens
                completion = self._client(key).chat.completions.create(**kwargs)
                return self._parse(completion)
            except AIError:
                raise
            except Exception as exc:  # noqa: BLE001 - mapped to a typed, secret-free error just below
                err = map_openai_error(exc, self.model)
            logger.warning("vision request failed: %s after %.1fs", err.code, time.monotonic() - started)
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

    def _parse(self, completion: Any) -> dict[str, Any]:
        try:
            text = completion.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise AIInvalidResponseError("huggingface response has no message content", provider=PROVIDER, model=self.model) from exc
        if not isinstance(text, str) or not text.strip():
            raise AIInvalidResponseError("huggingface returned an empty response", provider=PROVIDER, model=self.model)
        usage = getattr(completion, "usage", None)
        return {
            "text": text.strip(),
            "model": getattr(completion, "model", None) or self.model,
            "request_id": getattr(completion, "id", None),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else None,
        }
