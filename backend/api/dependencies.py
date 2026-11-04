from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, Request

from backend.database.connection import Database
from backend.evaluation.run_evaluation import RunEvaluationService
from backend.evaluation.service import EvaluationService
from backend.provenance.service import ProvenanceService
from backend.recovery.service import RecoveryService


@dataclass(frozen=True)
class Services:
    provenance: ProvenanceService
    recovery: RecoveryService
    evaluation: EvaluationService
    run_evaluation: RunEvaluationService


def build_services(database: Database) -> Services:
    provenance = ProvenanceService(database)
    return Services(
        provenance=provenance,
        recovery=RecoveryService(database),
        evaluation=EvaluationService(database),
        run_evaluation=RunEvaluationService(database, provenance),
    )


def get_services(request: Request) -> Services:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise RuntimeError("Application services are not initialized")
    return services


def sanitize_correlation_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:128]


def get_correlation_id(
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> str | None:
    return sanitize_correlation_id(correlation_id)