"""Hosted-API clients for Groq and Hugging Face (httpx only, no local inference).

Credentials are read from settings and sent only in the Authorization header.
Error messages are sanitized: no keys, prompts, or raw provider bodies.
"""

from __future__ import annotations

import base64
import logging
import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from .errors import (
    AIAuthError,
    AIConfigurationError,
    AIError,
    AIInvalidInputError,
    AIInvalidResponseError,
    AIModelUnavailableError,
    AIPayloadTooLargeError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
)

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 8.0


def classify_status(status: int, provider: str, model: str | None) -> AIError:
    kw = {"provider": provider, "model": model}
    if status in (401, 403):
        return AIAuthError(f"{provider} rejected the configured credentials", **kw)
    if status == 429:
        return AIRateLimitError(f"{provider} rate limit or quota reached", **kw)
    if status == 404:
        return AIModelUnavailableError(f"{provider} reports the model or endpoint is unavailable", **kw)
    if status == 413:
        return AIPayloadTooLargeError(f"{provider} rejected the payload as too large", **kw)
    if status in (400, 422):
        return AIInvalidInputError(f"{provider} rejected the request as invalid", **kw)
    if status == 408:
        return AITimeoutError(f"{provider} request timed out", **kw)
    if status >= 500:
        return AIProviderUnavailableError(f"{provider} is unavailable (HTTP {status})", **kw)
    return AIInvalidResponseError(f"{provider} returned unexpected HTTP {status}", **kw)


class _HostedClient:
    provider = "provider"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport
        self._sleep = sleep

    def _require_key(self) -> None:
        if not self._api_key:
            raise AIConfigurationError(f"{self.provider} credentials are not configured", provider=self.provider)

    def _post(
        self,
        url: str,
        *,
        model: str | None,
        retries: int,
        timeout: float | None = None,
        **request: Any,
    ) -> httpx.Response:
        """POST with bounded retries for transient errors only."""
        self._require_key()
        headers = {"Authorization": f"Bearer {self._api_key}"}
        attempt = 0
        while True:
            try:
                with httpx.Client(timeout=timeout or self._timeout, transport=self._transport) as client:
                    resp = client.post(url, headers=headers, **request)
                if resp.status_code < 400:
                    return resp
                err: AIError = classify_status(resp.status_code, self.provider, model)
            except httpx.TimeoutException:
                err = AITimeoutError(f"{self.provider} request timed out", provider=self.provider, model=model)
            except httpx.TransportError:
                err = AIProviderUnavailableError(
                    f"{self.provider} could not be reached", provider=self.provider, model=model
                )
            if not err.retryable or attempt >= retries:
                raise err
            attempt += 1
            delay = min(MAX_BACKOFF_SECONDS, 0.5 * 2 ** (attempt - 1))
            self._sleep(delay + random.uniform(0, min(0.25, delay)))

    @staticmethod
    def _json(resp: httpx.Response, provider: str, model: str | None) -> dict[str, Any]:
        try:
            body = resp.json()
        except ValueError as exc:
            raise AIInvalidResponseError(f"{provider} returned a non-JSON body", provider=provider, model=model) from exc
        if not isinstance(body, dict):
            raise AIInvalidResponseError(f"{provider} returned an unexpected body", provider=provider, model=model)
        return body

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        retries: int = 2,
        timeout: float | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """OpenAI-compatible chat completion; returns text, request id and usage."""
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = self._post(self._chat_url(), model=model, retries=retries, timeout=timeout, json=payload)
        body = self._json(resp, self.provider, model)
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIInvalidResponseError(
                f"{self.provider} response has no message content", provider=self.provider, model=model
            ) from exc
        if not isinstance(text, str) or not text.strip():
            raise AIInvalidResponseError(f"{self.provider} returned an empty response", provider=self.provider, model=model)
        return {
            "text": text,
            "model": body.get("model") or model,
            "request_id": body.get("id") or resp.headers.get("x-request-id"),
            "usage": body.get("usage") if isinstance(body.get("usage"), dict) else None,
        }


class GroqClient(_HostedClient):
    provider = "groq"

    def transcribe(
        self,
        model: str,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        retries: int = 2,
        timeout: float | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Groq audio transcription endpoint (multipart); never a chat endpoint."""
        data = {"model": model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            data["language"] = language
        resp = self._post(
            f"{self.base_url}/audio/transcriptions",
            model=model,
            retries=retries,
            timeout=timeout,
            data=data,
            files={"file": (filename, content, content_type)},
        )
        body = self._json(resp, self.provider, model)
        text = body.get("text")
        if not isinstance(text, str):
            raise AIInvalidResponseError("groq transcription has no text", provider=self.provider, model=model)
        return {
            "text": text.strip(),
            "language": body.get("language") if isinstance(body.get("language"), str) else None,
            "duration": body.get("duration") if isinstance(body.get("duration"), (int, float)) else None,
            "model": model,
            "request_id": resp.headers.get("x-request-id"),
        }

    def list_models(self) -> set[str]:
        """Model ids in the account's catalogue (used to verify availability)."""
        self._require_key()
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                resp = client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self._api_key}"})
        except httpx.TimeoutException as exc:
            raise AITimeoutError("groq request timed out", provider=self.provider) from exc
        except httpx.TransportError as exc:
            raise AIProviderUnavailableError("groq could not be reached", provider=self.provider) from exc
        if resp.status_code >= 400:
            raise classify_status(resp.status_code, self.provider, None)
        body = self._json(resp, self.provider, None)
        return {m["id"] for m in body.get("data", []) if isinstance(m, dict) and "id" in m}


class HuggingFaceClient(_HostedClient):
    provider = "huggingface"

    def vision_chat(
        self,
        model: str,
        prompt: str,
        image: bytes,
        image_type: str,
        *,
        retries: int = 2,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Chat completion with an image part, via the hosted Inference Providers router."""
        data_url = f"data:{image_type};base64,{base64.b64encode(image).decode()}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        return self.chat(model, messages, retries=retries, timeout=timeout, max_tokens=max_tokens)

    def segment(
        self,
        url: str,
        image: bytes,
        image_type: str,
        *,
        model: str | None = None,
        retries: int = 2,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """Hosted image-segmentation call (HF image-segmentation task output format).

        Returns the masks the endpoint produced; raises if it produced none.
        """
        self._require_key()
        resp = self._post_binary(url, image, image_type, model, retries, timeout)
        try:
            body = resp.json()
        except ValueError as exc:
            raise AIInvalidResponseError("huggingface returned a non-JSON body", provider=self.provider, model=model) from exc
        masks = [m for m in body if isinstance(m, dict) and m.get("mask")] if isinstance(body, list) else []
        if not masks:
            raise AIInvalidResponseError("segmentation returned no masks", provider=self.provider, model=model)
        return [
            {"label": m.get("label"), "score": m.get("score"), "mask_png_base64": m["mask"]} for m in masks
        ]

    def _post_binary(
        self, url: str, image: bytes, image_type: str, model: str | None, retries: int, timeout: float | None
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                with httpx.Client(timeout=timeout or self._timeout, transport=self._transport) as client:
                    resp = client.post(
                        url,
                        content=image,
                        headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": image_type},
                    )
                if resp.status_code < 400:
                    return resp
                err: AIError = classify_status(resp.status_code, self.provider, model)
            except httpx.TimeoutException:
                err = AITimeoutError("huggingface request timed out", provider=self.provider, model=model)
            except httpx.TransportError:
                err = AIProviderUnavailableError("huggingface could not be reached", provider=self.provider, model=model)
            if not err.retryable or attempt >= retries:
                raise err
            attempt += 1
            self._sleep(min(MAX_BACKOFF_SECONDS, 0.5 * 2 ** (attempt - 1)))
