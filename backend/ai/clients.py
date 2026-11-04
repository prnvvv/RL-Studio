"""The single hosted client for the Meta Model API (``https://api.meta.ai/v1``, one shared ``MODEL_API_KEY``).

* Text, vision and SAM segmentation go through the official OpenAI Python SDK, which Meta
  documents as compatible. The SDK is always constructed with an explicit ``api_key`` and Meta ``base_url`` so it can
  never reach another provider's default host. The SDK's own retries are disabled; bounded retries are implemented here.
* Voice transcription is a Meta-specific multipart endpoint (``POST /asr/transcribe``) and uses ``httpx`` directly.

Credentials are sent only in the Authorization header. Error messages are sanitized: no keys, prompts, audio, images or
raw provider bodies.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import logging
import random
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import openai

from .errors import (
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

logger = logging.getLogger(__name__)

PROVIDER = "meta"
MAX_BACKOFF_SECONDS = 8.0
#: optional request parameters Meta may reject for a given model; dropped once (and retried) when named in a HTTP 400
DROPPABLE_PARAMS = frozenset({"temperature", "max_output_tokens", "metadata", "reasoning", "response_format"})
SAM_METADATA = {"mask_encoding": "one_bit", "include_confidence": "true"}


def classify_status(status: int, model: str | None, body: Any = None) -> AIError:
    """Map a Meta HTTP status (and the documented error ``type``/``code``) to a typed, sanitized error."""
    kw = {"provider": PROVIDER, "model": model}
    err = body.get("error", body) if isinstance(body, dict) else {}
    etype = err.get("type") if isinstance(err, dict) else None
    if status == 401 or etype == "authentication_error":
        return AIAuthError("Meta rejected the configured MODEL_API_KEY", **kw)
    if status == 402 or etype == "billing_error":
        return AIQuotaError("Meta reports insufficient credits or no billing configured (HTTP 402)", **kw)
    if status == 403:
        return AIModelUnavailableError("the API key lacks permission for this model or feature (HTTP 403)", **kw)
    if status == 404:
        return AIModelUnavailableError("Meta reports the model or endpoint is unavailable to this account (HTTP 404)", **kw)
    if status == 429:
        return AIRateLimitError("Meta rate limit reached", **kw)
    if status == 413:
        return AIPayloadTooLargeError("Meta rejected the payload as too large", **kw)
    if status in (400, 406, 422):
        return AIInvalidInputError("Meta rejected the request as invalid", **kw)
    if status == 408:
        return AITimeoutError("Meta request timed out", **kw)
    if status >= 500:
        return AIProviderUnavailableError(f"Meta is unavailable (HTTP {status})", **kw)
    return AIInvalidResponseError(f"Meta returned unexpected HTTP {status}", **kw)


def _error_param(body: Any) -> str | None:
    err = body.get("error", body) if isinstance(body, dict) else None
    param = err.get("param") if isinstance(err, dict) else None
    return param if isinstance(param, str) else None


def _retry_after(headers: Any) -> float | None:
    try:
        return float(headers.get("retry-after")) if headers is not None and headers.get("retry-after") else None
    except (TypeError, ValueError):
        return None


class MetaClient:
    provider = PROVIDER

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 90.0,
        backoff: float = 1.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = (api_key or "").strip()
        self._timeout = timeout
        self._backoff = backoff
        self._transport = transport
        self._sleep = sleep
        self._sdk_client: openai.OpenAI | None = None

    # -- plumbing ---------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _require_key(self) -> None:
        if not self._api_key:
            raise AIConfigurationError("MODEL_API_KEY is not configured", provider=PROVIDER)

    def _sdk(self) -> openai.OpenAI:
        """OpenAI SDK pinned to the Meta base URL (the key is passed explicitly, never read from OPENAI_API_KEY)."""
        self._require_key()
        if self._sdk_client is None:
            http_client = httpx.Client(transport=self._transport, timeout=self._timeout) if self._transport else None
            self._sdk_client = openai.OpenAI(
                api_key=self._api_key, base_url=self.base_url, timeout=self._timeout, max_retries=0,
                http_client=http_client,
            )
        return self._sdk_client

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        base = retry_after if retry_after is not None else self._backoff * 2 ** (attempt - 1)
        base = min(MAX_BACKOFF_SECONDS, max(0.0, base))
        return base + random.uniform(0, min(0.25, base))

    def _translate(self, exc: Exception, model: str | None) -> tuple[AIError, float | None]:
        if isinstance(exc, openai.APITimeoutError):
            return AITimeoutError("Meta request timed out", provider=PROVIDER, model=model), None
        if isinstance(exc, openai.APIConnectionError):
            return AIProviderUnavailableError("Meta could not be reached", provider=PROVIDER, model=model), None
        if isinstance(exc, openai.APIStatusError):
            err = classify_status(exc.status_code, model, getattr(exc, "body", None))
            err.param = _error_param(getattr(exc, "body", None))  # type: ignore[attr-defined]
            return err, _retry_after(getattr(getattr(exc, "response", None), "headers", None))
        return AIProviderUnavailableError("unexpected provider failure", provider=PROVIDER, model=model), None

    def _call(self, model: str | None, retries: int, do: Callable[[], Any], droppable: dict[str, Any] | None = None) -> Any:
        """Run an SDK call with bounded retries for transient errors; drop one rejected optional parameter once."""
        attempt = 0
        while True:
            try:
                return do()
            except (openai.APIStatusError, openai.APIConnectionError) as exc:
                err, retry_after = self._translate(exc, model)
            param = getattr(err, "param", None)
            if droppable is not None and isinstance(err, AIInvalidInputError) and param in droppable and param in DROPPABLE_PARAMS:
                logger.info("meta rejected optional parameter %r; retrying without it", param)
                droppable.pop(param)
                continue
            if isinstance(err, AIRateLimitError) and not err.retryable:  # AIQuotaError: waiting does not help
                raise err
            if not err.retryable or attempt >= retries:
                raise err
            attempt += 1
            self._sleep(self._delay(attempt, retry_after))

    # -- text / vision (Responses API) --------------------------------------
    @staticmethod
    def _messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Meta applies the ``system`` role at the developer level; send ``developer`` as documented."""
        return [{**m, "role": "developer" if m.get("role") == "system" else m.get("role")} for m in messages]

    def respond(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        retries: int = 2,
        timeout: float | None = None,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Responses API call (``POST /responses``); returns text, request id and usage."""
        sdk = self._sdk().with_options(timeout=timeout or self._timeout, max_retries=0)
        params: dict[str, Any] = {"input": self._messages(messages)}
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens:
            params["max_output_tokens"] = max_tokens
        resp = self._call(model, retries, lambda: sdk.responses.create(model=model, **params), params)
        text = getattr(resp, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            raise AIInvalidResponseError("Meta returned an empty response", provider=PROVIDER, model=model)
        return {
            "text": text,
            "model": getattr(resp, "model", None) or model,
            "request_id": getattr(resp, "_request_id", None) or getattr(resp, "id", None),
            "usage": _usage(resp),
        }

    def vision_respond(
        self,
        model: str,
        prompt: str,
        image: bytes,
        image_type: str,
        *,
        retries: int = 2,
        timeout: float | None = None,
        max_tokens: int | None = None,
        instructions: str | None = None,
    ) -> dict[str, Any]:
        """Muse Spark image understanding: an ``input_image`` data URL inside a user message."""
        data_url = f"data:{image_type};base64,{base64.b64encode(image).decode('ascii')}"
        messages: list[dict[str, Any]] = []
        if instructions:
            messages.append({"role": "developer", "content": instructions})
        messages.append({"role": "user", "content": [
            {"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": data_url}]})
        return self.respond(model, messages, retries=retries, timeout=timeout, max_tokens=max_tokens)

    # -- voice (Muse Voice Transcribe) ---------------------------------------
    def transcribe(
        self, model: str, filename: str, wav: bytes, *, retries: int = 2, timeout: float | None = None,
        mode: str = "PUSH_TO_TALK", language_bias: list[str] | None = None, keywords: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """``POST /asr/transcribe``: multipart ``request`` (JSON settings) + ``audio`` (WAV); buffered JSON response."""
        self._require_key()
        settings: dict[str, Any] = {"model": model, "audioEncoding": "WAV", "mode": mode}
        if language_bias:
            settings["languageBias"] = language_bias
        if keywords:
            settings["keywords"] = keywords
        attempt = 0
        while True:
            err: AIError
            try:
                with httpx.Client(timeout=timeout or self._timeout, transport=self._transport) as client:
                    resp = client.post(
                        f"{self.base_url}/asr/transcribe",
                        params={"sessionId": session_id} if session_id else None,
                        headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
                        files={"request": (None, json.dumps(settings), "application/json"),
                               "audio": (filename, wav, "audio/wav")},
                    )
                if resp.status_code < 400:
                    break
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                err = classify_status(resp.status_code, model, body)
                retry_after = _retry_after(resp.headers)
            except httpx.TimeoutException:
                err, retry_after = AITimeoutError("Meta request timed out", provider=PROVIDER, model=model), None
            except httpx.TransportError:
                err, retry_after = AIProviderUnavailableError("Meta could not be reached", provider=PROVIDER, model=model), None
            if not err.retryable or attempt >= retries:  # AIQuotaError is never retryable
                raise err
            attempt += 1
            self._sleep(self._delay(attempt, retry_after))
        try:
            body = resp.json()
        except ValueError as exc:
            raise AIInvalidResponseError("Meta returned a non-JSON transcription", provider=PROVIDER, model=model) from exc
        text = body.get("transcript") if isinstance(body, dict) else None
        if not isinstance(text, str):
            raise AIInvalidResponseError("Meta transcription has no transcript", provider=PROVIDER, model=model)
        duration_ms = body.get("audioDurationMs")
        turns = [
            {"turn_id": t.get("turnId"), "start_ms": t.get("startMs"), "end_ms": t.get("endMs"),
             "transcript": t.get("transcript"), "speaker": t.get("speaker")}
            for t in body.get("turns", []) if isinstance(t, dict)
        ]
        return {
            "text": text.strip(),
            "duration": duration_ms / 1000 if isinstance(duration_ms, (int, float)) else None,
            "turns": turns,
            "model": model,
            "request_id": body.get("sessionId") if isinstance(body.get("sessionId"), str) else resp.headers.get("x-request-id"),
        }

    # -- segmentation (SAM 3.1 over the Responses API) ------------------------
    def segment(
        self, model: str, concept: str, media: bytes, media_type: str, *,
        retries: int = 2, timeout: float | None = None,
    ) -> dict[str, Any]:
        """Prompted image segmentation. The streamed special-token output is decoded by the official ``meta-sam-parser``.

        Returns the parser's records (boxes and masks; box ``x2``/``y2`` are half-open, i.e. exclusive, edges in source
        pixels; each mask raster is a PNG of the object's own size placed at the box's ``x1``/``y1``); a completed request with zero matches is a valid empty result,
        while an incomplete or failed stream raises.
        """
        sdk = self._sdk().with_options(timeout=timeout or self._timeout, max_retries=0)
        data_url = f"data:{media_type};base64,{base64.b64encode(media).decode('ascii')}"
        input_ = [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": concept}, {"type": "input_image", "image_url": data_url}]}]
        extra: dict[str, Any] = {"metadata": dict(SAM_METADATA)}

        def stream_events() -> list[Any]:
            kwargs = {"extra_body": {"metadata": extra["metadata"]}} if "metadata" in extra else {}
            with sdk.responses.create(model=model, input=input_, stream=True, **kwargs) as stream:
                return list(stream)

        events = self._call(model, retries, stream_events, extra)
        return _decode_segmentation(events, model)

    # -- catalogue ------------------------------------------------------------
    def list_models(self) -> set[str]:
        """Model ids enabled for this key's team (``GET /models``)."""
        sdk = self._sdk().with_options(max_retries=0)
        page = self._call(None, 1, lambda: sdk.models.list())
        return {m.id for m in getattr(page, "data", []) if getattr(m, "id", None)}


def _usage(resp: Any) -> dict[str, Any] | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    dump = getattr(usage, "model_dump", None)
    out = dump() if callable(dump) else usage
    return out if isinstance(out, dict) else None


def _event_dict(event: Any) -> Any:
    """Hand the parser plain attribute objects regardless of whether the SDK or a test produced the event."""
    if isinstance(event, dict):
        return SimpleNamespace(**event)
    return event


def _decode_segmentation(events: list[Any], model: str) -> dict[str, Any]:
    from meta_sam_parser import (
        ResponsesStreamError,
        decode_mask_to_raster,
        image_segmentation_format,
        parse_responses_stream,
    )

    types = [getattr(e, "type", None) if not isinstance(e, dict) else e.get("type") for e in events]
    if "response.output_text.delta" not in types and "response.output_text.done" not in types:
        # Documented: with no match the output lane is empty and no text events are sent. That is a valid empty
        # result only when the response itself completed; a stream that just stopped is an error.
        if types and types[-1] == "response.completed":
            return {"boxes": [], "masks": [], "count": 0, "raw_chars": 0}
        raise AIInvalidResponseError("the segmentation stream ended early (eof)", provider=PROVIDER, model=model)

    async def source() -> Any:
        for event in events:
            yield _event_dict(event)

    async def run() -> Any:
        return await parse_responses_stream(source(), image_segmentation_format()).final_result()

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(run())
        else:  # called from inside a running loop: parse on a worker thread with its own loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(asyncio.run, run()).result()
    except ResponsesStreamError as exc:
        raise AIInvalidResponseError("the segmentation stream failed", provider=PROVIDER, model=model) from exc
    outcome = result.outcome
    if getattr(outcome, "status", None) != "completed":
        raise AIInvalidResponseError(
            f"the segmentation stream ended early ({getattr(outcome, 'reason', 'incomplete')})", provider=PROVIDER, model=model)
    errors = [d for d in result.diagnostics if getattr(d, "severity", "") == "error"]
    if errors:
        raise AIInvalidResponseError(
            f"the segmentation output had {len(errors)} unreadable record(s) ({errors[0].code})", provider=PROVIDER, model=model)
    boxes: list[dict[str, Any]] = []
    masks: list[dict[str, Any]] = []
    for rec in result.records:
        if hasattr(rec, "left"):
            boxes.append({"object_id": rec.object_id, "x1": rec.left, "y1": rec.top, "x2": rec.right, "y2": rec.bottom,
                          "confidence": rec.confidence})
        elif hasattr(rec, "mask"):
            raster = decode_mask_to_raster(rec.mask)
            masks.append({
                "object_id": rec.object_id, "width": rec.mask.width, "height": rec.mask.height,
                "bounds": {"x1": rec.bounds.left, "y1": rec.bounds.top, "x2": rec.bounds.right, "y2": rec.bounds.bottom},
                "confidence": rec.confidence, "foreground_pixels": sum(raster),
                "mask_png_base64": _raster_png(raster, rec.mask.width, rec.mask.height),
            })
    return {"boxes": boxes, "masks": masks, "count": len({b["object_id"] for b in boxes} | {m["object_id"] for m in masks}),
            "raw_chars": len(result.raw_output)}


def _raster_png(raster: bytes, width: int, height: int) -> str:
    """A row-major 0/1 raster as a single-channel PNG (white = object)."""
    import io

    from PIL import Image

    img = Image.frombytes("L", (width, height), bytes(255 if b else 0 for b in raster))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
