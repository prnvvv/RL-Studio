"""In-memory implementation of the ``VerificationStorage`` protocol.

The store exists so the verification service can persist inputs, results and
reports without coupling to a database.  It is deliberately append-only: every
``save_*`` call returns a *new* storage ID and never mutates a previously
returned record, which keeps the audit trail intact.  Person 4 owns database
persistence; this implementation is the agreed local/test backend.
"""

from __future__ import annotations

import threading
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.verification.exceptions import PersistenceError
from backend.verification.models import (
    VerificationContext,
    VerificationInput,
    VerificationReport,
    VerificationResult,
)

_Model = TypeVar("_Model", bound=BaseModel)

INPUT_PREFIX = "vin"
RESULT_PREFIX = "vres"
REPORT_PREFIX = "vrep"


class InMemoryVerificationStore:
    """Thread-safe, append-only, in-memory ``VerificationStorage`` backend.

    Records are deep-copied on save and on load so callers cannot mutate stored
    history by accident.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._inputs: dict[str, VerificationInput] = {}
        self._contexts: dict[str, VerificationContext | None] = {}
        self._results: dict[str, VerificationResult] = {}
        self._reports: dict[str, VerificationReport] = {}
        self._counters: dict[str, int] = {
            INPUT_PREFIX: 0,
            RESULT_PREFIX: 0,
            REPORT_PREFIX: 0,
        }

    # -- helpers -----------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]:06d}"

    @staticmethod
    def _copy(model: _Model) -> _Model:
        return model.model_copy(deep=True)

    def _load(self, store: dict[str, _Model], storage_id: str, kind: str) -> _Model:
        if not isinstance(storage_id, str) or not storage_id:
            raise PersistenceError(
                f"Cannot load {kind}: storage_id must be a non-empty string.",
                details={"kind": kind},
            )
        with self._lock:
            record = store.get(storage_id)
        if record is None:
            raise PersistenceError(
                f"No {kind} stored under {storage_id!r}.",
                details={"kind": kind, "storage_id": storage_id},
            )
        return self._copy(record)

    # -- VerificationStorage ----------------------------------------------

    def save_verification_input(
        self,
        input_data: VerificationInput,
        context: VerificationContext | None = None,
    ) -> str:
        if not isinstance(input_data, VerificationInput):
            raise PersistenceError(
                "save_verification_input expects a VerificationInput instance.",
                details={"received": type(input_data).__name__},
            )
        with self._lock:
            storage_id = self._next_id(INPUT_PREFIX)
            self._inputs[storage_id] = self._copy(input_data)
            self._contexts[storage_id] = (
                self._copy(context)
                if isinstance(context, VerificationContext)
                else None
            )
        return storage_id

    def load_verification_input(self, storage_id: str) -> VerificationInput:
        return self._load(self._inputs, storage_id, "verification input")

    def load_verification_context(self, storage_id: str) -> VerificationContext | None:
        """Return the context saved with an input, if one was supplied."""
        if not isinstance(storage_id, str) or not storage_id:
            raise PersistenceError(
                "Cannot load context: storage_id must be a non-empty string.",
                details={"kind": "verification context"},
            )
        with self._lock:
            if storage_id not in self._inputs:
                raise PersistenceError(
                    f"No verification input stored under {storage_id!r}.",
                    details={"kind": "verification context", "storage_id": storage_id},
                )
            context = self._contexts.get(storage_id)
        return self._copy(context) if context is not None else None

    def save_verification_result(self, result: VerificationResult) -> str:
        if not isinstance(result, VerificationResult):
            raise PersistenceError(
                "save_verification_result expects a VerificationResult instance.",
                details={"received": type(result).__name__},
            )
        with self._lock:
            storage_id = self._next_id(RESULT_PREFIX)
            self._results[storage_id] = self._copy(result)
        return storage_id

    def load_verification_result(self, storage_id: str) -> VerificationResult:
        return self._load(self._results, storage_id, "verification result")

    def save_verification_report(self, report: VerificationReport) -> str:
        if not isinstance(report, VerificationReport):
            raise PersistenceError(
                "save_verification_report expects a VerificationReport instance.",
                details={"received": type(report).__name__},
            )
        with self._lock:
            storage_id = self._next_id(REPORT_PREFIX)
            self._reports[storage_id] = self._copy(report)
        return storage_id

    def load_verification_report(self, storage_id: str) -> VerificationReport:
        return self._load(self._reports, storage_id, "verification report")

    # -- introspection -----------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return shallow counts of stored records (never the records)."""
        with self._lock:
            return {
                "inputs": len(self._inputs),
                "results": len(self._results),
                "reports": len(self._reports),
            }

    def storage_ids(self) -> dict[str, list[str]]:
        """Return the stored identifiers in insertion order, per record type."""
        with self._lock:
            return {
                "inputs": list(self._inputs),
                "results": list(self._results),
                "reports": list(self._reports),
            }


__all__ = ["InMemoryVerificationStore"]
