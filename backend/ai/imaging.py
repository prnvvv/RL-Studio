"""Image preparation for the hosted vision and segmentation APIs.

Only validation and encoding happen locally (Pillow). No model is loaded and no pixel is ever interpreted by this
process: bytes are checked, then sent to the hosted provider. Local file paths are read here and never forwarded;
the provider only ever receives image bytes (as a data URL) or an https URL the caller supplied.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError

from .errors import AIInvalidInputError, AIPayloadTooLargeError

#: Pillow format name -> MIME type accepted by both hosted models
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
MAX_PIXELS = 25_000_000  # decompression-bomb guard (width * height)
MAX_URL_CHARS = 2048


@dataclass(frozen=True)
class ImageInfo:
    mime: str
    width: int
    height: int
    size_bytes: int


def inspect_image(content: bytes, max_bytes: int, *, declared_type: str | None = None) -> ImageInfo:
    """Validate size, real format (never the extension or declared type alone) and dimensions."""
    if not content:
        raise AIInvalidInputError("the image is empty")
    if len(content) > max_bytes:
        raise AIPayloadTooLargeError(f"the image exceeds the {max_bytes // (1024 * 1024)} MB limit")
    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt, width, height = img.format or "", img.width, img.height
            if fmt not in ALLOWED_FORMATS:
                raise AIInvalidInputError("unsupported image type (PNG, JPEG or WEBP required)")
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise AIInvalidInputError("the image dimensions are outside the supported range")
            img.verify()  # structural check without decoding the full image into the model
    except AIInvalidInputError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise AIInvalidInputError("the file is not a readable image") from exc
    mime = ALLOWED_FORMATS[fmt]
    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared and declared != mime:
        raise AIInvalidInputError("the image content does not match its declared type")
    return ImageInfo(mime, width, height, len(content))


def to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def read_image_file(path: str | Path, max_bytes: int) -> tuple[bytes, ImageInfo]:
    """Read a local image for upload. The path itself is never sent to a provider."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise AIInvalidInputError("the image file could not be read") from exc
    if not p.is_file():
        raise AIInvalidInputError("the image path is not a file")
    if size > max_bytes:
        raise AIPayloadTooLargeError(f"the image exceeds the {max_bytes // (1024 * 1024)} MB limit")
    try:
        content = p.read_bytes()
    except OSError as exc:
        raise AIInvalidInputError("the image file could not be read") from exc
    return content, inspect_image(content, max_bytes)


def validate_image_url(url: str) -> str:
    """An https URL for the provider to fetch. No credentials, no local/loopback hosts."""
    text = (url or "").strip()
    if not text or len(text) > MAX_URL_CHARS:
        raise AIInvalidInputError("the image URL is empty or too long")
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        raise AIInvalidInputError("only https image URLs are supported")
    if parts.username or parts.password:
        raise AIInvalidInputError("image URLs must not contain credentials")
    if host in {"localhost", "0.0.0.0"} or host.endswith((".local", ".internal")) or host.startswith(("127.", "10.", "192.168.", "169.254.")):
        raise AIInvalidInputError("image URLs must point to a public host")
    return text
