from __future__ import annotations
import os
import json
import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple, Any as AnyType

import httpx

from dotenv import load_dotenv
load_dotenv(".env", override=False)

from pydantic import BaseModel, Field, ValidationError

META_API_BASE = os.getenv("META_BASE_URL", "https://api.meta.ai/v1")
# API key check is lazy - do not raise at import time.
# MODEL_API_KEY = os.getenv("META_API")

DEFAULT_MODELS = ["muse-spark-1.3", "muse-wonder-1.0"]


class MetaAIProviderProtocol:
    """Protocol for a replaceable Meta Model API provider."""

    def invoke(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs: AnyType,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        ...  # pragma: no cover - implemented by concrete subclass


class MetaAIProviderDirect(MetaAIProviderProtocol):
    """Direct HTTP integration with the Meta Model API using httpx."""

    def __init__(self, base_url: str = META_API_BASE, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(60.0, connect=30.0),
        )
        self._last_request_id: Optional[str] = None
        self._last_usage: Optional[Dict[str, Any]] = None

    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        response = self.client.request(method, url, json=json, params=params, timeout=self.client.timeout)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise Exception("Invalid credentials - check META_API.")
        elif response.status_code == 429:
            raise Exception("Rate limit exceeded - please retry with backoff.")
        elif 500 <= response.status_code < 600:
            raise Exception(f"Meta API server error {response.status_code}.")
        else:
            raise Exception(f"API request failed {response.status_code}: {response.text}")

    def invoke(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs: AnyType,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        endpoint = "/v1/chat/completions"
        try:
            raw = self._request("POST", endpoint, json=payload)
        except Exception:
            endpoint = "/v1/responses"
            raw = self._request("POST", endpoint, json=payload)
        usage: Dict[str, Any] = {}
        if "usage" in raw:
            usage = raw.pop("usage")
        self._last_request_id = raw.get("id") or raw.get("request_id")
        self._last_usage = usage
        return raw, usage

    def close(self) -> None:
        self.client.close()


_HAS_LC = False
try:
    from langchain_openai import ChatOpenAI  # type: ignore[import]
    _HAS_LC = True
except Exception:  # broad; LangChain may not be installed or may lack the hook
    _HAS_LC = False  # type: ignore


if _HAS_LC:

    class MetaAIProviderLangChain(MetaAIProviderProtocol):
        """LangChain-based wrapper around the Meta Model API."""

        def __init__(
            self,
            model_name: str = os.getenv("META_MODEL", "muse-spark-1.3"),
            temperature: float = 0.0,
            **kwargs: AnyType,
        ) -> None:
            self.model_name = model_name
            self.temperature = temperature
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                openai_api_key=os.getenv("META_API", ""),
                openai_api_base=META_API_BASE,
                **kwargs,
            )

        def invoke(
            self,
            model: str,
            messages: List[Dict[str, Any]],
            *,
            temperature: Optional[float] = None,
            max_tokens: Optional[int] = None,
            response_format: Optional[Dict[str, Any]] = None,
            **kwargs: AnyType,
        ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            ai_msg = self.llm.invoke(
                messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens,
            )
            content = ai_msg.content if ai_msg.content else ""
            usage: Dict[str, Any] = {
                "prompt_tokens": getattr(ai_msg, "usage_metadata", {}).get("input_tokens", None),
                "completion_tokens": getattr(ai_msg, "usage_metadata", {}).get("output_tokens", None),
                "total_tokens": getattr(ai_msg, "usage_metadata", {}).get("total_tokens", None),
            }
            raw: Dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "choices": [
                    {"message": {"role": "assistant", "content": content}},
                    {"finish_reason": "stop"},
                ],
                "usage": usage,
                "model": model,
            }
            return raw, usage


def get_meta_ai_provider(
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    use_langchain: bool = True,
) -> MetaAIProviderProtocol:
    """Return a MetaAIProviderProtocol instance configured for the application's needs.

    The default strategy is:
    1. If use_langchain is True and LangChain is installed and the
       langchain_openai package is available, attempt a LangChain-based
       provider.
    2. Fall back to the direct HTTP SDK MetaAIProviderDirect.

    The returned provider can be injected into the verification agent,
    intent parser, planner, or any component that needs LLM access.
    """
    resolved_key = api_key or os.getenv("META_API")
    resolved_base = base_url or META_API_BASE

    if use_langchain and _HAS_LC:
        try:
            return MetaAIProviderLangChain(model=model or os.getenv("META_MODEL", "muse-spark-1.3"))
        except Exception as exc:
            logging.getLogger(__name__).warning(
                f"LangChain-based Meta provider could not be initialised: {exc}. "
                "Falling back to direct SDK."
            )

    return MetaAIProviderDirect(base_url=resolved_base, api_key=resolved_key)


def invoke_model(
    model: str,
    messages: List[Dict[str, Any]],
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    provider: Optional[MetaAIProviderProtocol] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """High-level helper that obtains a provider and invokes it.

    This is the function that the verification agent, intent parser, planner,
    and decision engine should call rather than constructing providers
    directly. It supports dependency injection so tests can supply a mock
    provider.

    If provider is None, the global factory get_meta_ai_provider is used.
    """
    prov = provider or get_meta_ai_provider()
    return prov.invoke(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )