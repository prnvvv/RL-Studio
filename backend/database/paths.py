"""Path safety and atomic file helpers for the artifact store.

Artifact paths are stored relative to the configured artifact root.  Absolute
paths, parent traversal, NUL bytes, and symlink escapes are rejected before any
file is read or written.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .exceptions import ArtifactPathError, IntegrityFailure
from .utils import sha256_file


def normalize_artifact_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or raw_path.strip() == "":
        raise ArtifactPathError("artifact_path must be a non-empty relative path")
    if "\x00" in raw_path or "\\" in raw_path:
        raise ArtifactPathError("artifact_path contains an unsupported character")
    path = Path(raw_path)
    if path.is_absolute() or path.anchor:
        raise ArtifactPathError("artifact_path must be relative to the artifact root")
    parts = path.parts
    if not parts or any(part in ("..", ".") for part in parts):
        raise ArtifactPathError("artifact_path must not contain parent traversal")
    return path.as_posix()


def resolve_artifact_path(root: Path, relative_path: str) -> Path:
    normalized = normalize_artifact_path(relative_path)
    root = root.resolve()
    candidate = (root / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        raise ArtifactPathError("artifact_path resolves outside the artifact root")
    return candidate


def read_artifact_bytes(
    root: Path, relative_path: str, *, max_bytes: int | None = None
) -> bytes:
    path = resolve_artifact_path(root, relative_path)
    if not path.is_file():
        raise ArtifactPathError("artifact file does not exist")
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise ArtifactPathError("artifact exceeds the configured size limit")
    return path.read_bytes()


def verify_file_hash(
    root: Path,
    relative_path: str,
    expected_hash: str,
    *,
    max_bytes: int | None = None,
) -> str:
    path = resolve_artifact_path(root, relative_path)
    if not path.is_file():
        raise IntegrityFailure("artifact file is missing")
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise ArtifactPathError("artifact exceeds the configured size limit")
    actual = sha256_file(path)
    if actual.lower() != expected_hash.lower():
        raise IntegrityFailure(
            "artifact content hash does not match the registered hash",
            details={"expected": expected_hash.lower(), "actual": actual},
        )
    return actual


def atomic_copy(source: Path, destination: Path) -> None:
    """Copy ``source`` to ``destination`` without exposing a partial file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        shutil.copyfile(source, tmp_path)
        with tmp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp_path, destination)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
