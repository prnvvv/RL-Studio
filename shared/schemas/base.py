"""Primitives shared by every schema module.

This module has no intra-package imports so that ``contracts``, ``events`` and
``requirements`` can depend on it without importing the package ``__init__``
(which would create a circular import).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"
"""Canonical schema version for all shared contracts in this package."""


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    """Return a freshly generated stable identifier string (UUIDv4)."""
    return str(uuid.uuid4())


__all__ = ["SCHEMA_VERSION", "utc_now", "new_uuid"]
