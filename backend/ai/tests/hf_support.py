"""Shared helpers for the hosted vision / segmentation tests (no network, no credentials)."""

from __future__ import annotations

import base64
import io
from typing import Any

import httpx2
from PIL import Image

from backend.ai.diagnostics import probe_image

SECRET = "hf_test_secret_value_do_not_leak"


def png_bytes(size: tuple[int, int] = (32, 24), color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def mask_b64(size: tuple[int, int] = (32, 24), covered: tuple[int, int, int, int] | None = (0, 0, 16, 12)) -> str:
    img = Image.new("L", size, 0)
    if covered:
        img.paste(255, covered)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def http_response(status: int, body: Any = None) -> httpx2.Response:
    request = httpx2.Request("POST", "https://router.huggingface.co/v1/chat/completions")
    return httpx2.Response(status, json=body if body is not None else {"error": "x"}, request=request)


__all__ = ["SECRET", "http_response", "mask_b64", "png_bytes", "probe_image"]
