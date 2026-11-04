"""Evidence-grounded investigation context built only from persisted records.

``IncidentContextBuilder`` reads the incident and everything the existing subsystems already persist about it (run,
provenance, impact analysis, artifacts/checkpoints, the verification and its failing results, earlier recoveries, and
the Studio evidence catalogue). It invents nothing: each piece of evidence gets a stable reference string that exists
in the persisted records, and ``evidence_index`` is the set the model is allowed to cite. A context with no usable
evidence is marked insufficient so no model call is made.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.database.connection import Database
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import recoveries as recoveries_repo
from backend.database.repositories import runs as runs_repo
from backend.provenance.service import ProvenanceService
from backend.verification.storage.sqlite_store import SqliteVerificationStore

MAX_ARTIFACTS = 30
MAX_FAILED_RESULTS = 20
MAX_TEXT = 600
#: ``(run_id) -> {"catalogue": ..., "missing": [...]}`` from the Studio evidence builder; ``None`` when unavailable
CatalogueProvider = Callable[[str], dict[str, Any] | None]


def _clip(value: Any, limit: int = MAX_TEXT) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "...(truncated)"
    return value


@dataclass
class IncidentContext:
    incident_id: str
    run_id: str
    payload: dict[str, Any]
    #: every reference the model may cite -> what it points to
    evidence_index: dict[str, str] = field(default_factory=dict)
    #: deterministic gaps (not model opinions)
    missing_evidence: list[str] = field(default_factory=list)
    #: checkpoint id / artifact id -> integrity and incident-impact facts for deterministic recovery checks
    candidate_checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)
    sufficient: bool = False
    context_hash: str = ""
    prior_investigation_id: str | None = None


class IncidentContextBuilder:
    def __init__(
        self,
        database: Database,
        provenance: ProvenanceService,
        verification_store: SqliteVerificationStore | None = None,
        catalogue_provider: CatalogueProvider | None = None,
    ) -> None:
        self.database = database
        self.provenance = provenance
        self.store = verification_store or SqliteVerificationStore(database)
        self.catalogue_provider = catalogue_provider

    def build(self, incident_id: str, *, prior: dict[str, Any] | None = None) -> IncidentContext:
        incident = self.provenance.get_incident(incident_id)  # raises IncidentNotFoundError
        index: dict[str, str] = {}
        missing: list[str] = []
        payload: dict[str, Any] = {}

        def cite(ref: str, what: str) -> str:
            index[ref] = what
            return ref

        payload["incident"] = {
            "ref": cite(f"incident:{incident.incident_id}", "the incident record"),
            "status": incident.status, "severity": incident.severity, "detection_method": incident.detection_method,
            "summary": _clip(incident.summary), "environment_id": incident.environment_id,
            "environment_version": incident.environment_version,
            "source_environment_version": incident.source_environment_version,
            "fault_type": incident.fault_type,
            "corruption_start_timestep": incident.corruption_start_timestep,
            "corruption_end_timestep": incident.corruption_end_timestep,
            "requirement_id": incident.requirement_id, "created_at": incident.created_at.isoformat(),
            "evidence_ids": [cite(e, "evidence recorded on the incident") for e in incident.evidence_ids[:50]],
        }
        if not incident.evidence_ids:
            missing.append("the incident records no evidence references")

        with self.database.read() as conn:
            run = runs_repo.get_run(conn, incident.run_id)
            artifacts = artifacts_repo.list_artifacts_for_run(conn, incident.run_id)
            recoveries = recoveries_repo.list_recoveries_for_incident(conn, incident_id)
        if run is None:
            missing.append("the incident's run record was not found")
        else:
            payload["run"] = {
                "ref": cite(f"run:{run['run_id']}", "the run record"), "status": run.get("status"),
                "environment_id": run.get("environment_id"), "environment_version": run.get("environment_version"),
                "agent_config_fingerprint": run.get("agent_config_fingerprint"),
            }

        affected: set[str] = set()
        try:
            impact = self.provenance.get_incident_impact(incident_id)
            affected = set(impact.affected_artifact_ids) | set(impact.affected_checkpoint_ids)
            payload["impact"] = {
                "ref": cite(f"impact:{impact.impact_id}", "the deterministic impact analysis"),
                "status": impact.impact_status.value, "score": impact.impact_score,
                "affected_artifact_ids": impact.affected_artifact_ids[:50],
                "affected_trajectory_ids": impact.affected_trajectory_ids[:50],
                "affected_policy_update_ids": impact.affected_policy_update_ids[:50],
                "affected_checkpoint_ids": impact.affected_checkpoint_ids[:50], "warnings": impact.warnings[:10],
            }
            for ref in impact.evidence_ids[:50]:
                cite(ref, "evidence recorded by the impact analysis")
            if impact.impact_status.value == "unknown_incomplete_lineage":
                missing.append("impact analysis is incomplete: the lineage does not prove which experiences are affected")
        except Exception:  # noqa: BLE001 - a missing/failed analysis is a gap, not a reason to fail the diagnosis
            missing.append("no impact analysis is available for this incident")

        try:
            trace = self.provenance.get_run_provenance(incident.run_id)
            payload["provenance"] = {
                "ref": cite(f"provenance:{trace.provenance_id}", "the run's provenance trace"),
                "status": trace.provenance_status.value, "lineage_completeness": trace.lineage_completeness.value,
                "artifact_count": trace.artifact_count, "warnings": trace.warnings[:10],
            }
            if trace.lineage_completeness.value != "complete":
                missing.append(f"the run's provenance lineage is {trace.lineage_completeness.value}")
        except Exception:  # noqa: BLE001
            missing.append("no provenance trace is available for the run")

        candidates: dict[str, dict[str, Any]] = {}
        ordered = sorted(artifacts, key=lambda a: a.get("artifact_type") != "checkpoint")[:MAX_ARTIFACTS]
        payload["artifacts"] = []
        for art in ordered:
            aid = art["artifact_id"]
            row = {
                "ref": cite(f"artifact:{aid}", f"a persisted {art.get('artifact_type')} artifact"),
                "type": art.get("artifact_type"), "status": art.get("artifact_status"),
                "integrity_status": art.get("integrity_status"), "timestep": art.get("timestep"),
                "environment_version": art.get("environment_version"), "checkpoint_id": art.get("checkpoint_id"),
                "trajectory_id": art.get("trajectory_id"), "affected_by_incident": aid in affected,
            }
            payload["artifacts"].append(row)
            if art.get("artifact_type") == "checkpoint":
                info = {"artifact_id": aid, "checkpoint_id": art.get("checkpoint_id"),
                        "integrity_status": art.get("integrity_status"), "timestep": art.get("timestep"),
                        "affected_by_incident": aid in affected or art.get("checkpoint_id") in affected}
                candidates[aid] = info
                if art.get("checkpoint_id"):
                    candidates[art["checkpoint_id"]] = info
                    cite(f"checkpoint:{art['checkpoint_id']}", "a recorded checkpoint")
                    cite(art["checkpoint_id"], "a recorded checkpoint id")
        if len(artifacts) > MAX_ARTIFACTS:
            payload["artifacts_omitted"] = len(artifacts) - MAX_ARTIFACTS
        if not artifacts:
            missing.append("no artifacts or checkpoints are recorded for the run")

        failed_results: list[dict[str, Any]] = []
        if incident.verification_id:
            ver = self.store.get_verification(incident.verification_id)
            if ver is None:
                missing.append("the incident's verification record was not found")
            else:
                vref = cite(f"verification:{ver['verification_id']}", "the verification execution")
                for res in self.store.get_results(incident.verification_id):
                    if str(res.get("status", "")).lower() == "pass":
                        continue
                    rref = cite(f"verification_result:{ver['verification_id']}/{res['requirement_id']}",
                                "a non-passing deterministic verification result")
                    for ev in res.get("evidence_refs") or []:
                        cite(str(ev), "evidence referenced by a verification result")
                    failed_results.append({
                        "ref": rref, "requirement_id": res["requirement_id"], "status": res.get("status"),
                        "expected": _clip(res.get("expected")), "actual": _clip(res.get("actual")),
                        "evidence_refs": [str(e) for e in (res.get("evidence_refs") or [])[:20]],
                        "details": _clip(json.dumps(res.get("details") or {}, default=str)),
                    })
                payload["verification"] = {
                    "ref": vref, "overall_status": ver.get("overall_status"),
                    "note": "statuses are the deterministic engine's; they are facts, not model output",
                    "non_passing_results": failed_results[:MAX_FAILED_RESULTS],
                }
        else:
            missing.append("the incident has no linked verification")

        payload["recoveries"] = [
            {"ref": cite(f"recovery:{r['recovery_id']}", "an earlier recovery record"),
             "status": r.get("recovery_status"), "strategy": r.get("recovery_strategy"),
             "source_checkpoint_id": r.get("source_checkpoint_id")} for r in recoveries[:10]]

        catalogue = None
        if self.catalogue_provider is not None:
            try:
                catalogue = self.catalogue_provider(incident.run_id)
            except Exception:  # noqa: BLE001 - metrics/events are optional evidence
                catalogue = None
        if catalogue:
            payload["run_evidence_catalogue"] = catalogue.get("catalogue")
            missing += [str(m) for m in (catalogue.get("missing") or [])][:10]
        else:
            missing.append("run metrics and events were not available to this investigation")

        if prior is not None:
            payload["prior_root_cause_analysis"] = {
                "investigation_id": prior["investigation_id"],
                "result": prior["result"],
                "note": "a previous advisory analysis (model inference), not verified evidence",
            }

        sufficient = bool(failed_results or artifacts or incident.evidence_ids)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return IncidentContext(
            incident_id=incident_id, run_id=incident.run_id, payload=payload, evidence_index=index,
            missing_evidence=list(dict.fromkeys(missing)), candidate_checkpoints=candidates, sufficient=sufficient,
            context_hash=digest, prior_investigation_id=prior["investigation_id"] if prior else None,
        )
