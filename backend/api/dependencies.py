from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Header, Request

from backend.database.connection import Database
from backend.evaluation.service import EvaluationService
from backend.provenance.service import ProvenanceService
from backend.recovery.service import RecoveryService


@dataclass(frozen=True)
class Services:
    provenance: ProvenanceService
    recovery: RecoveryService
    evaluation: EvaluationService


def build_services(database: Database) -> Services:
    return Services(
        provenance=ProvenanceService(database),
        recovery=RecoveryService(database),
        evaluation=EvaluationService(database),
    )


def get_services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise RuntimeError("Application services are not initialized")
    return services


def sanitize_correlation_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:128]


def get_correlation_id(
    correlation_id: Annotated[
        Optional[str], Header(alias="X-Correlation-ID")
    ] = None,
) -> Optional[str]:
    return sanitize_correlation_id(correlation_id)
