"""Small, dependency-free helpers shared by Person 4 modules."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def loads(value: Optional[str], default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_sha256(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("artifact_hash must be a 64-character hexadecimal SHA-256 value")
    return normalized
