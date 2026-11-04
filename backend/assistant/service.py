"""The assistant: a general RL helper that is never gated on an incident, plus an incident-scoped investigator chat.

Both modes call the shared ``AIService`` (Meta Model API) and nothing else. The context given to the model is built only
from persisted records and is bounded; what was (and was not) available is returned to the caller so the answer can be
checked against it. The assistant decides nothing: verdicts, incidents and recoveries stay with their own services.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from backend.ai.errors import AIUnsupportedTaskError
from backend.ai.registry import Task
from backend.ai.service import AIService
from backend.database.connection import Database
from backend.database.repositories import incidents as incidents_repo
from backend.diagnosis.context import CatalogueProvider, IncidentContextBuilder
from backend.evaluation.run_evaluation import RunEvaluationService
from backend.projects.repository import ProjectRepository
from backend.provenance.service import ProvenanceService
from backend.training_history import TrainingHistory
from backend.verification.storage.sqlite_store import SqliteVerificationStore

from .prompts import PROMPT_VERSION, build_messages

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000
MAX_HISTORY = 20
MAX_CONTEXT_CHARS = 14000
RequirementsProvider = Callable[[str], list[dict[str, Any]]]


class AssistantError(Exception):
    http_status = 422

    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status


def _clip_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned = [{"role": h["role"], "content": h["content"][:MAX_MESSAGE_CHARS]} for h in history
               if h.get("role") in {"user", "assistant"} and (h.get("content") or "").strip()]
    return cleaned[-MAX_HISTORY:]


def _fit(context: dict[str, Any]) -> dict[str, Any]:
    """Keep the serialised context inside the budget by dropping the bulkiest optional sections first."""
    for key in ("evaluations", "requirements", "verifications", "incidents", "evidence_catalogue"):
        if len(json.dumps(context, default=str)) <= MAX_CONTEXT_CHARS:
            break
        if key in context:
            context[key] = context[key][:3] if isinstance(context[key], list) else {"truncated": True}
            context.setdefault("truncated_sections", []).append(key)
    return context


class AssistantService:
    def __init__(
        self,
        database: Database,
        provenance: ProvenanceService,
        ai: AIService,
        *,
        requirements_provider: RequirementsProvider | None = None,
        catalogue_provider: CatalogueProvider | None = None,
    ) -> None:
        self.database = database
        self.ai = ai
        self.provenance = provenance
        self.history = TrainingHistory(database)
        self.evaluations = RunEvaluationService(database, provenance)
        self.requirements = requirements_provider
        self.incident_builder = IncidentContextBuilder(database, provenance, SqliteVerificationStore(database), catalogue_provider)

    # ------------------------------------------------------------------ context
    def _project_context(self, project_id: str | None, run_id: str | None) -> tuple[dict[str, Any], list[str], list[str]]:
        """(context, sources used, things not available). Only persisted records; nothing is inferred."""
        context: dict[str, Any] = {}
        sources: list[str] = []
        missing: list[str] = []
        if project_id is None:
            missing.append("no project is selected, so no project data is available")
            return context, sources, missing
        project = ProjectRepository(self.database).get_project(project_id)
        if project is None:
            raise AssistantError("project_not_found", "The project was not found.", 404)
        context["project"] = {k: project.get(k) for k in ("project_id", "name", "description", "agent", "environment")}
        sources.append(f"project {project['name']}")
        if self.requirements is not None:
            reqs = self.requirements(project_id)
            context["requirements"] = [
                {k: r.get(k) for k in ("requirement_id", "status", "statement", "text", "metric", "operator", "threshold", "origin")
                 if r.get(k) is not None} for r in reqs[:20]]
            sources.append(f"{len(reqs)} requirement(s)")
        selected = run_id is not None
        run = self.history.get_run(project_id, run_id) if run_id else self.history.latest_run(project_id)
        if run_id and run is None:
            raise AssistantError("run_not_found", "The run was not found in this project.", 404)
        if run is None:
            missing.append("the project has no training run yet")
            return _fit(context), sources, missing
        rid = run["run_id"]
        snapshots = self.history.snapshots(rid)
        context["run"] = {
            "selected_by_user": selected, **{k: run.get(k) for k in (
                "run_id", "name", "algorithm", "environment_name", "status", "termination_reason", "total_timesteps",
                "total_episodes", "final_metrics", "error", "started_at", "finished_at", "agent_version", "environment_config_version")},
            "agent_snapshot": snapshots.get("agent"), "environment_snapshot": snapshots.get("environment"),
            "training_snapshot": snapshots.get("training"),
        }
        sources.append(f"run {rid}" + ("" if selected else " (most recent; none selected)"))
        evaluations = self.evaluations.list_for_run(rid)
        context["evaluations"] = [
            {"run_evaluation_id": e["run_evaluation_id"], "status": e["status"], "purpose": e["purpose"], "artifact_id": e["artifact_id"],
             "policy_fingerprint": (e["policy_fingerprint"] or "")[:16] or None, "environment_version": e["environment_version"],
             "episode_count": e["episode_count"], "seeds": e["seeds"][:3], "summary": (e["metrics"] or {}).get("summary"),
             "variability": (e["metrics"] or {}).get("variability"), "created_at": e["created_at"]} for e in evaluations[:5]]
        if not evaluations:
            missing.append("this run's saved policy has not been evaluated yet")
        with self.database.read() as conn:
            incidents = incidents_repo.list_incidents_for_run(conn, rid)
        context["incidents"] = [{"incident_id": i["incident_id"], "status": i["status"], "severity": i.get("severity"),
                                 "summary": (i.get("summary") or "")[:300], "requirement_id": i.get("requirement_id")} for i in incidents[:10]]
        verifications = SqliteVerificationStore(self.database).list_verifications(rid)
        context["verifications"] = [{"verification_id": v["verification_id"], "overall_status": v["overall_status"],
                                     "created_at": v["created_at"]} for v in verifications[:5]]
        if not verifications:
            missing.append("no verification has been run against this run")
        sources.append(f"{len(evaluations)} evaluation(s), {len(verifications)} verification(s), {len(incidents)} incident(s)")
        return _fit(context), sources, missing

    def _incident_context(self, incident_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        built = self.incident_builder.build(incident_id)
        payload = json.loads(json.dumps(built.payload, default=str))
        return {"incident_evidence": payload, "evidence_index": built.evidence_index,
                "missing_evidence": built.missing_evidence}, {"run_id": built.run_id, "sufficient": built.sufficient}

    # ------------------------------------------------------------------ chat
    def chat(self, *, message: str, history: list[dict[str, str]] | None = None, project_id: str | None = None,
             run_id: str | None = None, incident_id: str | None = None) -> dict[str, Any]:
        message = (message or "").strip()
        if not message:
            raise AssistantError("empty_message", "Write a message first.")
        if len(message) > MAX_MESSAGE_CHARS:
            raise AssistantError("message_too_long", f"Messages are limited to {MAX_MESSAGE_CHARS} characters.")
        history = _clip_history(history or [])
        incident_mode = incident_id is not None
        sources: list[str]
        missing: list[str]
        if incident_mode:
            context, meta = self._incident_context(incident_id)  # type: ignore[arg-type]
            sources, missing = [f"incident {incident_id}"], list(context.get("missing_evidence") or [])
            if meta["sufficient"] is False:
                missing.append("the incident has too little persisted evidence for a grounded analysis")
        else:
            context, sources, missing = self._project_context(project_id, run_id)
        note: str | None = None
        messages = build_messages(message, history, context, incident=incident_mode)
        task = Task.INVESTIGATION if incident_mode else Task.GENERAL
        try:
            result = self.ai.run_text(task, messages)
        except AIUnsupportedTaskError as exc:
            if not incident_mode:
                raise
            # Muse Wonder is a preview model that may be switched off for this account: say so, answer with Spark.
            note = f"The investigation model is unavailable ({exc}); this answer came from the standard model."
            task = Task.GENERAL
            result = self.ai.run_text(task, messages)
        return {
            "reply": result.text.strip(),
            "mode": "incident" if incident_mode else "general",
            "task": task.value, "model": result.model, "fallback_used": result.fallback_used,
            "prompt_version": PROMPT_VERSION, "note": note,
            "context": {"project_id": project_id, "run_id": (context.get("run") or {}).get("run_id") if not incident_mode else None,
                        "incident_id": incident_id, "sources": sources, "not_available": missing},
        }
