"""Mapping between the internal ``CheckStatus`` lattice and the external
contract-status vocabulary defined by the repository contracts.

The verification subsystem keeps a single authoritative enum
(``backend.verification.models.CheckStatus``).  Downstream consumers
(incidents, API payloads, UI) describe outcomes as ``pass``, ``violation``,
``not_evaluable`` or ``inconclusive``.  Keeping the mapping in one tested
place avoids re-defining enums in several modules (AGENTS.md §7.3, Gate B).
"""

from __future__ import annotations

from backend.verification.models import CheckStatus

#: Contract status vocabulary used by incident/API consumers.
CONTRACT_STATUSES: frozenset[str] = frozenset(
    {"pass", "violation", "not_evaluable", "inconclusive"}
)

#: Deterministic mapping from internal status to contract status.
CONTRACT_STATUS_MAP: dict[CheckStatus, str] = {
    CheckStatus.PASS: "pass",
    CheckStatus.FAIL: "violation",
    CheckStatus.UNKNOWN: "not_evaluable",
    CheckStatus.BLOCKED: "not_evaluable",
    CheckStatus.PENDING: "inconclusive",
    CheckStatus.ERROR: "inconclusive",
}


def to_contract_status(status: CheckStatus | str) -> str:
    """Return the contract-status string for *status*.

    Raises:
        ValueError: if *status* is not a known ``CheckStatus`` value.
    """
    if isinstance(status, str):
        try:
            status = CheckStatus(status)
        except ValueError as exc:
            raise ValueError(f"Unknown check status: {status!r}") from exc
    try:
        return CONTRACT_STATUS_MAP[status]
    except KeyError as exc:  # pragma: no cover - exhaustive mapping
        raise ValueError(f"Unknown check status: {status!r}") from exc


__all__ = ["CONTRACT_STATUSES", "CONTRACT_STATUS_MAP", "to_contract_status"]
