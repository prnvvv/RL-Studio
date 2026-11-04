"""Incident diagnosis, root-cause investigation and recovery recommendation (advisory).

One service over the existing subsystems: the persisted incident and provenance records, the Phase 3 verification
store, and the shared hosted ``AIService`` (Muse Wonder for these reasoning tasks). It adds no second AI client, no
second incident model and no recovery executor. Recommendations never execute anything: recovery still goes through
the existing assessment -> approval -> execution contracts in ``backend/recovery``.
"""

from __future__ import annotations

from typing import Any

from backend.ai.errors import AIError
from backend.ai.service import AIService
from backend.database.connection import Database
from backend.provenance.service import ProvenanceService
from backend.verification.storage.sqlite_store import SqliteVerificationStore

from .context import CatalogueProvider, IncidentContextBuilder
from .graph import build_diagnosis_graph
from .models import KIND_RECOVERY_PLAN, KIND_ROOT_CAUSE
from .store import InvestigationStore


class InvestigationNotFound(LookupError):
    pass


class DiagnosisService:
    def __init__(
        self,
        database: Database,
        provenance: ProvenanceService,
        ai: AIService,
        *,
        catalogue_provider: CatalogueProvider | None = None,
    ) -> None:
        self.database = database
        self.ai = ai
        self.store = InvestigationStore(database)
        self.builder = IncidentContextBuilder(
            database, provenance, SqliteVerificationStore(database), catalogue_provider)
        self._graph: Any = None

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_diagnosis_graph(self)
        return self._graph

    def _run(self, incident_id: str, kind: str, force: bool) -> dict[str, Any]:
        state = self.graph.invoke({"incident_id": incident_id, "kind": kind, "force": force, "trail": []})
        error = state.get("error")
        if isinstance(error, AIError):
            raise error  # the provider failure is reported as such; nothing is persisted or fabricated
        record = dict(state["record"])
        record["reused"] = state.get("outcome") == "reused"
        record["trail"] = state.get("trail", [])
        return record

    def investigate(self, incident_id: str, *, force: bool = False) -> dict[str, Any]:
        """Evidence-grounded root-cause investigation of a persisted incident (Muse Wonder)."""
        return self._run(incident_id, KIND_ROOT_CAUSE, force)

    def recommend_recovery(self, incident_id: str, *, force: bool = False) -> dict[str, Any]:
        """Advisory recovery recommendations, informed by the latest root-cause analysis when one exists."""
        return self._run(incident_id, KIND_RECOVERY_PLAN, force)

    def list(self, incident_id: str) -> list[dict[str, Any]]:
        self.builder.provenance.get_incident(incident_id)  # 404 for an unknown incident
        return self.store.list_for_incident(incident_id)

    def get(self, incident_id: str, investigation_id: str) -> dict[str, Any]:
        rec = self.store.get(investigation_id)
        if rec is None or rec["incident_id"] != incident_id:
            raise InvestigationNotFound(investigation_id)
        return rec
