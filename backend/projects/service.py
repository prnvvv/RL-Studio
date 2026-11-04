"""Project management service.

It owns projects, intent documents and the project <-> run association, and nothing else. Every
requirement-related step is delegated to the existing Phase 3 ``VerificationLifecycle``:

* a project requirement is an ordinary ``verification_requirements`` row scoped to the pseudo run
  ``project:<project_id>`` (so it can exist before any training run);
* the same ``IntentInterpreter`` / ``rv.validate_proposal`` / confirmation rules process it;
* verifying against a run *binds* the confirmed requirement to that run (a new run-scoped row that preserves
  the confirmed text and source) and calls the unchanged ``VerificationLifecycle.execute``. PASS/FAIL/UNKNOWN
  therefore come only from the deterministic engine, with evidence from that run alone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from typing import Any

from backend.ai.service import AIService
from backend.database.connection import Database
from backend.database.utils import utc_now_iso
from backend.projects import documents as docs
from backend.projects.repository import ProjectRepository
from backend.provenance.service import ProvenanceService
from backend.studio.store import TrajectoryReader
from backend.verification.incidents.sink import IncidentSink
from backend.verification.input.studio_evidence import StudioEvidence
from backend.verification.intent import requirement_validation as rv
from backend.verification.intent.ai_interpreter import MAX_STATEMENT_CHARS
from backend.verification.lifecycle.service import (
    PROJECT_SCOPE_PREFIX,
    Conflict,
    InvalidRequest,
    NotFound,
    PreparedEvidence,
    RunNotFound,
    VerificationLifecycle,
)
from backend.verification.models import RequirementSource, VerificationRequirement

logger = logging.getLogger(__name__)

NAME_MAX = 120
DESCRIPTION_MAX = 2000
CONFIG_MAX_BYTES = 8192
MAX_SEGMENTS = 10
CHUNK_CHARS = 3800
ACTIVE_RUN_STATUSES = {"running", "paused", "stopping"}
TERMINAL_RUN_STATUSES = {"completed", "stopped", "failed"}
_NS = uuid.NAMESPACE_URL
_CONFIRMED_LIFECYCLE = (rv.CONFIRMED, rv.VERIFIED, rv.FAILED, rv.UNKNOWN)
_LIVE_LIFECYCLE = (rv.DRAFT, rv.NEEDS_CLARIFICATION, *_CONFIRMED_LIFECYCLE)
_PROJECT_ID = re.compile(r"^prj_[0-9a-f]{16}$")


def scope_for(project_id: str) -> str:
    return f"{PROJECT_SCOPE_PREFIX}{project_id}"


def _sha(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, separators=(",", ":"), default=str).encode())
        h.update(b"\x1f")
    return h.hexdigest()


def split_segments(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries into pieces of at most ``limit`` characters. Nothing is dropped."""
    pieces: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text.strip()):
        para = para.strip()
        if not para:
            continue
        while len(para) > limit:  # one huge paragraph: cut at a sentence/space near the limit
            cut = max(para.rfind(". ", 0, limit), para.rfind(" ", 0, limit))
            cut = cut + 1 if cut > limit // 2 else limit
            head, para = para[:cut].strip(), para[cut:].strip()
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        if len(current) + len(para) + 2 > limit and current:
            pieces.append(current)
            current = ""
        current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def _clean_config(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidRequest(f"{field} must be an object")
    if len(json.dumps(value, default=str)) > CONFIG_MAX_BYTES:
        raise InvalidRequest(f"{field} is too large", {"max_bytes": CONFIG_MAX_BYTES})
    return value


class ProjectService:
    def __init__(
        self,
        *,
        database: Database,
        reader: TrajectoryReader,
        provenance: ProvenanceService,
        ai: AIService | None = None,
        incident_sink: IncidentSink | None = None,
    ) -> None:
        self.database = database
        self.reader = reader
        self.repo = ProjectRepository(database)
        self.lifecycle = VerificationLifecycle(
            database=database, reader=reader, provenance=provenance, ai=ai, incident_sink=incident_sink,
            scope_resolver=self._resolve_scope,
        )
        self.store = self.lifecycle.store

    # ---- project scope as (evidence-free) facts ------------------------------------------------------------
    def _resolve_scope(self, scope_id: str) -> PreparedEvidence:
        project_id = scope_id[len(PROJECT_SCOPE_PREFIX):]
        project = self.repo.get_project(project_id)
        if project is None:
            raise RunNotFound("the project does not exist", {"project_id": project_id})
        agent, env = project["agent"], project["environment"]
        config = rv.flatten_config({
            "environment_config": env.get("env_params") or {},
            "training_config": {**(env.get("training") or {}), "agent_params": agent.get("agent_params") or {}},
        })
        facts = rv.EvidenceFacts(
            run_id=None, environment_id=env.get("environment"), environment_version=env.get("environment_version"),
            episode_count=0, event_count=0, event_types=frozenset(), metric_names=frozenset(), metric_count=0,
            config=config, missing_evidence=("no_run_selected",),
        )
        evidence = StudioEvidence(payload={}, missing_evidence=["no_run_selected"])
        return PreparedEvidence(evidence, facts, _sha(project_id, env, agent))

    # ---- helpers -------------------------------------------------------------------------------------------
    def _require(self, project_id: str) -> dict[str, Any]:
        project = self.repo.get_project(project_id) if _PROJECT_ID.match(project_id) else None
        if project is None:
            raise NotFound("project not found", {"project_id": project_id[:40]})
        return project

    def _run_status(self, run: dict[str, Any]) -> str:
        studio = self.reader.get_run(run["run_id"])
        return str((studio or {}).get("status") or run.get("status") or "unknown")

    def _require_project_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        run = self.repo.get_run(run_id)
        if run is None or run.get("project_id") != project_id:
            raise NotFound("run not found in this project", {"run_id": run_id[:60]})
        return run

    # ---- projects ---------------------------------------------------------------------------------------------
    def create_project(self, name: str, description: str | None = None, agent: dict[str, Any] | None = None,
                       environment: dict[str, Any] | None = None) -> dict[str, Any]:
        name = " ".join((name or "").split())
        if not name or len(name) > NAME_MAX:
            raise InvalidRequest(f"name is required and at most {NAME_MAX} characters")
        if description is not None and len(description) > DESCRIPTION_MAX:
            raise InvalidRequest(f"description is at most {DESCRIPTION_MAX} characters")
        project_id = f"prj_{uuid.uuid4().hex[:16]}"
        self.repo.insert_project(project_id, name, (description or "").strip() or None,
                                 _clean_config(agent, "agent"), _clean_config(environment, "environment"))
        return self.get_project(project_id)

    def update_project(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        self._require(project_id)
        changes: dict[str, Any] = {}
        if "name" in fields:
            name = " ".join(str(fields["name"] or "").split())
            if not name or len(name) > NAME_MAX:
                raise InvalidRequest(f"name is required and at most {NAME_MAX} characters")
            changes["name"] = name
        if "description" in fields:
            desc = fields["description"]
            if desc is not None and len(desc) > DESCRIPTION_MAX:
                raise InvalidRequest(f"description is at most {DESCRIPTION_MAX} characters")
            changes["description"] = (desc or "").strip() or None
        for key in ("agent", "environment"):
            if key in fields:
                changes[key] = _clean_config(fields[key], key)
        if changes:  # the id never changes, so every associated record is untouched
            self.repo.update_project(project_id, **changes)
        return self.get_project(project_id)

    def delete_project(self, project_id: str, confirm_name: str) -> dict[str, Any]:
        project = self._require(project_id)
        if " ".join((confirm_name or "").split()) != project["name"]:
            raise Conflict("type the exact project name to confirm deletion", {"project_id": project_id})
        active = [r["run_id"] for r in self.repo.project_runs(project_id) if self._run_status(r) in ACTIVE_RUN_STATUSES]
        if active:
            raise Conflict("stop the active training run before deleting the project", {"active_runs": active})
        self.repo.soft_delete(project_id)
        return {
            "project_id": project_id, "status": "deleted",
            "retained": ("runs, training data, evidence, verifications, incidents and uploaded documents are kept; "
                         "the project is only hidden"),
        }

    def list_projects(self) -> list[dict[str, Any]]:
        return [self._summary(p) for p in self.repo.list_projects()]

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._summary(self._require(project_id), detail=True)

    def _summary(self, project: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
        pid = project["project_id"]
        runs = self.repo.project_runs(pid)
        statuses = [self._run_status(r) for r in runs]
        active = sum(s in ACTIVE_RUN_STATUSES for s in statuses)
        reqs = self.store.list_requirements(run_id=scope_for(pid))
        live = [r for r in reqs if r["lifecycle_status"] in _LIVE_LIFECYCLE]
        verifications = self.repo.run_verifications(pid)
        out = {
            "project_id": pid, "name": project["name"], "description": project["description"],
            "status": project["status"], "created_at": project["created_at"], "updated_at": project["updated_at"],
            "agent": project["agent"], "environment": project["environment"],
            "training": {
                "state": "not_started" if not runs else "active" if active else "completed",
                "run_count": len(runs), "active_runs": active,
                "completed_runs": sum(s == "completed" for s in statuses),
            },
            "requirements": {
                "total": len(live), "confirmed": sum(r["lifecycle_status"] in _CONFIRMED_LIFECYCLE for r in live),
                "pending": sum(r["lifecycle_status"] in (rv.DRAFT, rv.NEEDS_CLARIFICATION) for r in live),
            },
            "last_verification": None if not verifications else {
                "run_id": verifications[-1]["run_id"], "status": verifications[-1]["evaluation_status"],
                "at": verifications[-1]["created_at"]},
            "verification_count": len({v["verification_id"] for v in verifications}),
        }
        if detail:
            out["document_count"] = len(self.repo.list_documents(pid))
        return out

    # ---- documents ----------------------------------------------------------------------------------------------
    def add_document(self, project_id: str, filename: str, content_type: str | None, data: bytes) -> tuple[dict[str, Any], bool]:
        """Returns (record, duplicate). A file with the wrong type/signature/size is rejected and not stored."""
        self._require(project_id)
        try:
            docs.validate_upload(filename, content_type, data)
        except docs.DocumentError as exc:
            raise InvalidRequest(exc.message, exc.details) from exc
        digest = hashlib.sha256(data).hexdigest()
        existing = self.repo.find_document_by_hash(project_id, digest)
        if existing is not None:
            return self._document_view(existing), True
        document_id = f"doc_{uuid.uuid4().hex[:16]}"
        reference = f"project_documents/{project_id}/{document_id}.bin"
        target = self.database.config.artifact_root / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)  # original kept for audit; the name is never used as a path
        status, error, text = "extracted", None, None
        try:
            text = docs.extract_text(filename, content_type, data).text
        except docs.DocumentError as exc:
            status, error = "failed", exc.message
        self.repo.insert_document({
            "document_id": document_id, "project_id": project_id, "filename": docs.safe_filename(filename),
            "content_type": (content_type or "application/octet-stream").split(";")[0].strip().lower(),
            "size_bytes": len(data), "sha256": digest, "storage_reference": reference,
            "extraction_status": status, "extraction_error": error, "extracted_text": text,
            "text_chars": len(text or ""),
        })
        self.repo.touch(project_id)
        return self._document_view(self.repo.get_document(project_id, document_id)), False  # type: ignore[arg-type]

    @staticmethod
    def _document_view(rec: dict[str, Any], *, with_text: bool = False) -> dict[str, Any]:
        keys = ("document_id", "project_id", "filename", "content_type", "size_bytes", "sha256",
                "storage_reference", "extraction_status", "extraction_error", "text_chars", "created_at")
        view = {k: rec[k] for k in keys}
        view["preview"] = (rec.get("extracted_text") or "")[:300] or None
        if with_text:
            view["extracted_text"] = rec.get("extracted_text")
        return view

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        self._require(project_id)
        return [self._document_view(d) for d in self.repo.list_documents(project_id)]

    # ---- intent -> requirements -------------------------------------------------------------------------------------
    def _stage(self, project_id: str, run_id: str | None) -> str:
        if run_id:
            run = self._require_project_run(project_id, run_id)
            return "during_training" if self._run_status(run) in ACTIVE_RUN_STATUSES else "post_training"
        return "pre_training" if not self.repo.project_runs(project_id) else "project_level"

    def submit_intent(
        self, project_id: str, statement: str | None, document_ids: list[str] | None = None,
        run_id: str | None = None, idempotency_key: str | None = None, supersedes: str | None = None,
    ) -> dict[str, Any]:
        project = self._require(project_id)
        statement = (statement or "").strip()
        document_ids = list(dict.fromkeys(document_ids or []))
        if not statement and not document_ids:
            raise InvalidRequest("provide an expectation, a document, or both")
        stage = self._stage(project_id, run_id)

        sources: list[tuple[str, dict[str, Any]]] = []  # (text, source reference)
        if statement:
            for i, chunk in enumerate(split_segments(statement)):
                sources.append((chunk, {"type": "text", "chunk": i}))
        for doc_id in document_ids:
            doc = self.repo.get_document(project_id, doc_id)
            if doc is None:
                raise NotFound("document not found in this project", {"document_id": doc_id[:40]})
            if doc["extraction_status"] != "extracted" or not doc["extracted_text"]:
                raise InvalidRequest("the document has no extracted text", {"document_id": doc_id, "reason": doc["extraction_error"]})
            for i, chunk in enumerate(split_segments(doc["extracted_text"])):
                sources.append((chunk, {"type": "document", "document_id": doc_id, "filename": doc["filename"], "chunk": i,
                                        "sha256": doc["sha256"]}))
        if len(sources) > MAX_SEGMENTS:
            raise InvalidRequest(f"the input is too long: {len(sources)} parts, at most {MAX_SEGMENTS} per submission; split it",
                                 {"parts": len(sources), "max": MAX_SEGMENTS})
        too_long = [s for s, _ in sources if len(s) > MAX_STATEMENT_CHARS]
        if too_long:  # defensive: split_segments already bounds this
            raise InvalidRequest("a part exceeds the interpreter limit")

        old = None
        revision, key = 1, None
        if supersedes:
            old = self.repo.requirement_link(project_id, supersedes)
            if old is None:
                raise NotFound("requirement not found in this project", {"requirement_id": supersedes[:60]})
            revision, key = old["requirement_revision"] + 1, old["requirement_key"]

        scope = scope_for(project_id)
        base_ctx: dict[str, Any] = {"project_id": project_id, "stage": stage}
        if project["environment"].get("environment_version"):
            base_ctx["environment_version"] = project["environment"]["environment_version"]
        if project["environment"].get("environment"):
            base_ctx["environment"] = project["environment"]["environment"]
        if project["agent"].get("agent"):
            base_ctx["agent"] = project["agent"]["agent"]

        intents: list[dict[str, Any]] = []
        for index, (text, source) in enumerate(sources):
            ctx = {**base_ctx, "source": source}
            idem = None if not idempotency_key else f"{idempotency_key}:{index}"
            view = self.lifecycle.submit_intent(scope, text, ctx, idem)
            self.repo.link_intent(view["intent_id"], project_id, stage, run_id,
                                  [source["document_id"]] if source["type"] == "document" else [], source)
            for req in view["requirements"]:
                self.repo.link_requirement(req["requirement_id"], project_id, key or req["requirement_id"], revision,
                                           supersedes, stage, source)
            intents.append(view)

        created = [r["requirement_id"] for v in intents for r in v["requirements"]]
        if supersedes and len(created) != 1:
            for rid in created:  # nothing was confirmed: withdraw the ambiguous proposals, keep the history
                self.lifecycle.reject_requirement(rid, "revision did not produce exactly one requirement")
            raise InvalidRequest("a revision must describe exactly one requirement", {"proposed": len(created)})
        self.repo.touch(project_id)
        return {
            "project_id": project_id, "stage": stage, "run_id": run_id,
            "intents": [self._intent_view(project_id, v) for v in intents],
            "requirement_count": len(created),
        }

    def _intent_view(self, project_id: str, view: dict[str, Any]) -> dict[str, Any]:
        conflicts, superseded = self._conflicts(project_id), self._superseded(project_id)
        links = {link["requirement_id"]: link for link in self.repo.requirement_links(project_id)}
        intent_link = next((i for i in self.repo.intent_links(project_id) if i["intent_id"] == view["intent_id"]), None)
        return {
            **view,
            "stage": intent_link["stage"] if intent_link else None,
            "source": intent_link["source"] if intent_link else {},
            "linked_run_id": intent_link["run_id"] if intent_link else None,
            "requirements": [self._requirement_view(r, links.get(r["requirement_id"]), conflicts, superseded)
                             for r in view["requirements"]],
        }

    def list_intents(self, project_id: str) -> list[dict[str, Any]]:
        self._require(project_id)
        return [self._intent_view(project_id, self.lifecycle.get_intent(link["intent_id"]))
                for link in self.repo.intent_links(project_id)]

    # ---- requirements ---------------------------------------------------------------------------------------------------
    def _records(self, project_id: str) -> list[dict[str, Any]]:
        return self.store.list_requirements(run_id=scope_for(project_id))

    def _superseded(self, project_id: str) -> set[str]:
        by_id = {r["requirement_id"]: r for r in self._records(project_id)}
        return {
            link["supersedes_requirement_id"] for link in self.repo.requirement_links(project_id)
            if link["supersedes_requirement_id"] and
            by_id.get(link["requirement_id"], {}).get("lifecycle_status") in _CONFIRMED_LIFECYCLE
        }

    def _conflicts(self, project_id: str) -> dict[str, list[str]]:
        superseded = self._superseded(project_id)
        live = [r for r in self._records(project_id)
                if r["lifecycle_status"] in _LIVE_LIFECYCLE and r["requirement_id"] not in superseded]
        reqs = [VerificationRequirement.model_validate(r["requirement"]) for r in live]
        out: dict[str, list[str]] = {}
        for ids, _why in rv.find_contradictions(reqs):
            for rid in ids:
                out.setdefault(rid, []).extend(i for i in ids if i != rid)
        return out

    def _requirement_view(self, rec_view: dict[str, Any], link: dict[str, Any] | None, conflicts: dict[str, list[str]],
                          superseded: set[str] | None = None) -> dict[str, Any]:
        rid = rec_view["requirement_id"]
        validation_status = rec_view.get("validation_status")
        return {
            **rec_view,
            "project_id": link["project_id"] if link else None,
            "requirement_key": link["requirement_key"] if link else rid,
            "requirement_revision": link["requirement_revision"] if link else 1,
            "supersedes": link["supersedes_requirement_id"] if link else None,
            "superseded": rid in (superseded or set()),
            "stage": link["stage"] if link else None,
            "source": link["source"] if link else {},
            "conflicts_with": sorted(set(conflicts.get(rid, []))),
            "awaiting_run_evidence": validation_status == rv.V_NOT_EVALUABLE
            and rec_view["lifecycle_status"] in (rv.DRAFT, rv.CONFIRMED),
        }

    def list_requirements(self, project_id: str) -> list[dict[str, Any]]:
        self._require(project_id)
        links = {link["requirement_id"]: link for link in self.repo.requirement_links(project_id)}
        conflicts, superseded = self._conflicts(project_id), self._superseded(project_id)
        latest = {v["requirement_id"]: v for v in self.repo.run_verifications(project_id)}  # last row wins
        out = []
        for rec in self._records(project_id):
            view = self._requirement_view(self.lifecycle.requirement_view(rec), links.get(rec["requirement_id"]), conflicts, superseded)
            last = latest.get(rec["requirement_id"])
            view["latest_verification"] = None if last is None else {
                "verification_id": last["verification_id"], "run_id": last["run_id"],
                "status": last["evaluation_status"], "stage": last["stage"], "at": last["created_at"]}
            out.append(view)
        return out

    def _own_requirement(self, project_id: str, requirement_id: str) -> dict[str, Any]:
        self._require(project_id)
        link = self.repo.requirement_link(project_id, requirement_id)
        if link is None:
            raise NotFound("requirement not found in this project", {"requirement_id": requirement_id[:60]})
        return link

    def confirm_requirement(self, project_id: str, requirement_id: str, overrides: dict[str, Any] | None) -> dict[str, Any]:
        link = self._own_requirement(project_id, requirement_id)
        clashes = self._conflicts(project_id).get(requirement_id)
        if clashes:
            raise Conflict("this requirement contradicts another; reject one of them first",
                           {"requirement_id": requirement_id, "conflicts_with": sorted(set(clashes))})
        view = self.lifecycle.confirm_requirement(requirement_id, overrides)
        self.repo.touch(project_id)
        return self._requirement_view(view, link, self._conflicts(project_id), self._superseded(project_id))

    def reject_requirement(self, project_id: str, requirement_id: str, reason: str | None) -> dict[str, Any]:
        link = self._own_requirement(project_id, requirement_id)
        view = self.lifecycle.reject_requirement(requirement_id, reason)
        self.repo.touch(project_id)
        return self._requirement_view(view, link, self._conflicts(project_id), self._superseded(project_id))

    # ---- runs -------------------------------------------------------------------------------------------------------------------
    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        self._require(project_id)
        out = []
        for run in self.repo.project_runs(project_id):
            studio = self.reader.get_run(run["run_id"]) or {}
            out.append({
                "run_id": run["run_id"], "project_id": project_id, "status": self._run_status(run),
                "environment_id": run.get("environment_id"), "environment_version": run.get("environment_version"),
                "agent": (run.get("metadata") or {}).get("agent") or studio.get("agent"),
                "session_id": studio.get("session_id"), "name": studio.get("name"),
                "episode_count": studio.get("episode_count"), "step_count": studio.get("step_count"),
                "created_at": run["created_at"], "finished_at": studio.get("finished_at"),
            })
        return out

    def legacy_runs(self) -> list[dict[str, Any]]:
        return [{"run_id": r["run_id"], "environment_id": r.get("environment_id"), "status": self._run_status(r),
                 "created_at": r["created_at"]} for r in self.repo.legacy_runs()]

    def adopt_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        self._require(project_id)
        run = self.repo.get_run(run_id)
        if run is None:
            raise NotFound("run not found", {"run_id": run_id[:60]})
        if run.get("project_id"):
            raise Conflict("this run already belongs to a project", {"run_id": run_id})
        if not self.repo.adopt_run(project_id, run_id):
            raise Conflict("this run already belongs to a project", {"run_id": run_id})
        self.repo.touch(project_id)
        return {"run_id": run_id, "project_id": project_id}

    # ---- verification against a run -----------------------------------------------------------------------------------------------
    def _current_confirmed(self, project_id: str, ids: list[str] | None) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        links = {link["requirement_id"]: link for link in self.repo.requirement_links(project_id)}
        superseded = self._superseded(project_id)
        recs = {r["requirement_id"]: r for r in self._records(project_id)}

        def is_confirmed(rec: dict[str, Any]) -> bool:
            return rec["lifecycle_status"] in _CONFIRMED_LIFECYCLE and \
                rec["requirement"].get("source") == RequirementSource.developer_confirmed.value

        if ids is not None:
            bad = {i: ("not_found_in_project" if i not in links else "not_confirmed") for i in ids
                   if i not in links or not is_confirmed(recs[i])}
            if bad:
                raise Conflict("some requirements cannot be verified", {"requirements": bad})
            return [(recs[i], links[i]) for i in dict.fromkeys(ids)]
        return [(rec, links[rid]) for rid, rec in recs.items() if rid in links and is_confirmed(rec) and rid not in superseded]

    def _bind(self, project_id: str, link: dict[str, Any], rec: dict[str, Any], run_id: str,
              prepared: PreparedEvidence) -> tuple[str | None, str | None]:
        """Run-scoped copy of a confirmed project requirement. Returns (run_requirement_id, skip_reason)."""
        existing = self.repo.get_binding(rec["requirement_id"], run_id)
        if existing is not None:
            return existing["run_requirement_id"], None
        req = VerificationRequirement.model_validate(rec["requirement"])
        md = dict(req.metadata or {})
        run_req_id = str(uuid.uuid5(_NS, f"rl-studio:bind:{rec['requirement_id']}:{run_id}"))
        md.update(run_id=run_id, project_id=project_id, project_requirement_id=rec["requirement_id"],
                  project_requirement_revision=link["requirement_revision"],
                  environment_id=prepared.facts.environment_id)
        bound = req.model_copy(update={"id": run_req_id, "metadata": md})
        applied = md.get("user_supplied_overrides") or []
        stated = rv.normalize_ws(" ".join([rec["source_statement"], *(f"{k} {md.get(k)}" for k in applied),
                                           *(str(getattr(req, k)) for k in ("expected_value", "tolerance") if k in applied)]))
        outcome = rv.validate_proposal(bound, prepared.facts, run_id=run_id, source_statement=rec["source_statement"], user_statement=stated)
        if outcome.status in (rv.V_INVALID, rv.V_CLARIFY):
            return None, "; ".join(outcome.reasons) or outcome.status
        intent_id = str(uuid.uuid5(_NS, f"rl-studio:bound-intent:{project_id}:{run_id}"))
        if self.store.get_intent(intent_id) is None:
            self.store.save_intent({
                "intent_id": intent_id, "run_id": run_id, "environment_id": prepared.facts.environment_id,
                "environment_version": prepared.facts.environment_version,
                "original_text": f"Confirmed project requirements bound to run {run_id}", "context": {"project_id": project_id},
                "status": "interpreted", "status_reason": None, "interpretation": {}, "ai": {"origin": "project_requirement"},
                "idempotency_key": f"bound:{project_id}:{run_id}", "source_refs": {"project_id": project_id, "run_id": run_id},
            })
        record = self.lifecycle._record(bound, intent_id, run_id, prepared.facts, rec["source_statement"], rv.CONFIRMED,
                                        outcome.status, {**outcome.to_dict(), "bound_from": rec["requirement_id"]})
        self.store.save_requirement(record)
        self.store.update_requirement(run_req_id, confirmed_at=rec.get("confirmed_at") or utc_now_iso())
        self.repo.insert_binding(rec["requirement_id"], run_id, project_id, run_req_id, intent_id)
        return run_req_id, None

    def verify(self, project_id: str, run_id: str, requirement_ids: list[str] | None = None,
               idempotency_key: str | None = None) -> dict[str, Any]:
        self._require(project_id)
        run = self._require_project_run(project_id, run_id)
        chosen = self._current_confirmed(project_id, requirement_ids)
        if not chosen:
            raise Conflict("this project has no confirmed requirement to verify; confirm at least one first", {"project_id": project_id})
        run_status = self._run_status(run)
        prepared = self.lifecycle.prepare_evidence(run_id)
        window = {
            "episodes": prepared.facts.episode_count, "events": prepared.facts.event_count,
            "step_count": (self.reader.get_run(run_id) or {}).get("step_count"),
            "evidence_fingerprint": prepared.fingerprint, "run_status": run_status,
        }
        stage = "during_training" if run_status in ACTIVE_RUN_STATUSES else "post_training"
        if run_status in ACTIVE_RUN_STATUSES and prepared.facts.episode_count < 1:
            return {"project_id": project_id, "run_id": run_id, "state": "waiting_for_evidence", "stage": stage,
                    "reason": "the run has not completed an episode yet; nothing is evaluated until evidence exists",
                    "evaluation_window": window, "verification": None, "skipped": {}}
        bound: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        skipped: dict[str, str] = {}
        for rec, link in chosen:
            run_req_id, reason = self._bind(project_id, link, rec, run_id, prepared)
            if run_req_id is None:
                skipped[rec["requirement_id"]] = reason or "not applicable to this run"
            else:
                bound[run_req_id] = (rec, link)
        if not bound:
            raise Conflict("none of the requirements apply to this run", {"skipped": skipped})
        verification = self.lifecycle.execute(run_id, list(bound), idempotency_key)
        for result in self.lifecycle.get_results(verification["verification_id"]):
            rec, link = bound[result["requirement_id"]]
            self.repo.record_run_verification({
                "project_id": project_id, "run_id": run_id, "verification_id": verification["verification_id"],
                "requirement_id": rec["requirement_id"], "requirement_revision": link["requirement_revision"],
                "run_requirement_id": result["requirement_id"], "evaluation_status": result["status"],
                "stage": stage, "run_status": run_status, "evidence_references": result.get("evidence_refs") or [],
                "evaluation_window": window,
            })
        self.repo.touch(project_id)
        return {"project_id": project_id, "run_id": run_id, "state": "evaluated", "stage": stage,
                "interim": run_status in ACTIVE_RUN_STATUSES, "evaluation_window": window,
                "verification": verification, "skipped": skipped}

    def list_verifications(self, project_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
        self._require(project_id)
        if run_id:
            self._require_project_run(project_id, run_id)
        return self.repo.run_verifications(project_id, run_id)

    def run_verification_detail(self, project_id: str, verification_id: str) -> dict[str, Any]:
        self._require(project_id)
        rows = [v for v in self.repo.run_verifications(project_id) if v["verification_id"] == verification_id]
        if not rows:
            raise NotFound("verification not found in this project", {"verification_id": verification_id[:60]})
        return self.lifecycle.get_verification(verification_id)


__all__ = ["ProjectService", "scope_for", "split_segments"]
