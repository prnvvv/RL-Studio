"""Verification storage backends.

Only an in-memory backend is provided here.  Database persistence belongs to
Person 4's ``backend/database/`` module; this package implements the agreed
``VerificationStorage`` protocol without creating an independent database.
"""

from __future__ import annotations

from backend.verification.storage.verification_store import InMemoryVerificationStore

__all__ = ["InMemoryVerificationStore"]
