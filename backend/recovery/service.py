from __future__ import annotations

import sqlite3
from typing import Any, Optional

from backend.database.connection import Database
from backend.database.exceptions import IntegrityFailure, OperationLockedError
from backend.database.paths import atomic_copy, resolve_artifact_path, verify_file_hash
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import audit as audit_repo
from backend.database.repositories import locks as locks_repo
from backend.database.repositories import recoveries as recoveries_repo
from backend.database.repositories import runs as runs_repo
from backend.database.utils import (
    dumps,
    new_id,
    sha256_file,
    unique_preserving_order,
    utc_now_iso,
)
from backend.provenance.models import ImpactAnalysis, Incident
from backend.provenance.service import ProvenanceService

from .exceptions import (
    AssessmentNotFoundError,
    RecoveryConflictError,
    RecoveryNotFoundError,
)
from .models import (
    Approval,
    CheckOutcome,
    CompatibilityCheck,
    Recovery,
    RecoveryAssessment,
    RecoveryAssessmentRequest,
    RecoveryCreateRequest,
    RecoveryEligibility,
    RecoveryStrategy,
)

PASS = CheckOutcome.pass_.value
FAIL = CheckOutcome.fail.value
UNKNOWN = CheckOutcome.unknown.value
BLOCKED = CheckOutcome.blocked.value
SKIPPED = CheckOutcome.skipped.value

REQUIRED_CONTINUATION_COMPONENTS = (
    "policy",
    "optimizer",
    "rng",
    "counters",
)


def _check(
    name: str,
    outcome: str,
    detail: str,
    evidence_ids: Optional[list[str]] = None,
) -> CompatibilityCheck:
    return CompatibilityCheck(
        name=name,
        outcome=CheckOutcome(outcome),
        detail=detail,
        evidence_ids=evidence_ids or [],
    )


def _resolve_checkpoint(
    conn: sqlite3.Connection, identifier: Optional[str]
) -> dict[str, Any] | None:
    if not identifier:
        return None
    artifact = artifacts_repo.get_artifact(conn, identifier)
    if artifact is not None:
        return artifact
    return artifacts_repo.get_artifact_by_checkpoint_id(conn, identifier)


class RecoveryService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.provenance = ProvenanceService(database)

    # ------------------------------------------------------------------
    # Assessment
    # ------------------------------------------------------------------
    def _build_assessment(
        self,
        *,
        incident: Incident,
        impact: ImpactAnalysis,
        run_agent_fingerprint: Optional[str],
        checkpoint: Optional[dict[str, Any]],
        request: RecoveryAssessmentRequest,
    ) -> dict[str, Any]:
        checks: list[CompatibilityCheck] = []
        warnings: list[str] = []
        lineage_gaps: list[str] = []
        target_environment_version = (
            request.target_environment_version or incident.environment_version
        )
        target_agent_fingerprint = (
            request.target_agent_config_fingerprint or run_agent_fingerprint
        )

        if request.recovery_strategy is not RecoveryStrategy.restore_checkpoint:
            checks.append(
                _check(
                    "checkpoint_requirement",
                    SKIPPED,
                    "This strategy does not select a checkpoint in the MVP.",
                )
            )
            if impact.impact_status.value == "unknown_incomplete_lineage":
                checks.append(
                    _check(
                        "impact_evidence",
                        UNKNOWN,
                        "Impact analysis is incomplete; recovery scope is unproven.",
                    )
                )
                lineage_gaps.append("incident impact classification is incomplete")
            else:
                checks.append(
                    _check(
                        "impact_evidence",
                        PASS,
                        f"Impact analysis status is {impact.impact_status.value}.",
                    )
                )
            eligibility = (
                RecoveryEligibility.needs_review
                if any(check.outcome.value == UNKNOWN for check in checks)
                else RecoveryEligibility.eligible
            )
            return {
                "recovery_eligibility": eligibility.value,
                "recovery_strategy": request.recovery_strategy.value,
                "recovery_reason": request.recovery_reason
                or "Recovery strategy selected without automatic checkpoint execution.",
                "source_checkpoint_id": None,
                "target_environment_version": target_environment_version,
                "target_agent_config_fingerprint": target_agent_fingerprint,
                "compatibility": [check.model_dump(mode="json") for check in checks],
                "lineage_gaps": lineage_gaps,
                "evidence_ids": unique_preserving_order(
                    [*request.evidence_ids, *impact.evidence_ids]
                ),
                "warnings": warnings,
                "errors": [],
                "details": {
                    "source_artifact_id": None,
                    "strategy_execution_supported": False,
                },
            }

        if checkpoint is None:
            checks.append(
                _check(
                    "source_checkpoint_exists",
                    FAIL,
                    "No source checkpoint was selected. The latest checkpoint is "
                    "not assumed to be safe.",
                )
            )
            return {
                "recovery_eligibility": RecoveryEligibility.ineligible.value,
                "recovery_strategy": request.recovery_strategy.value,
                "recovery_reason": request.recovery_reason
                or "No compatible source checkpoint was identified.",
                "source_checkpoint_id": None,
                "target_environment_version": target_environment_version,
                "target_agent_config_fingerprint": target_agent_fingerprint,
                "compatibility": [check.model_dump(mode="json") for check in checks],
                "lineage_gaps": ["source checkpoint not selected or not found"],
                "evidence_ids": unique_preserving_order(
                    [*request.evidence_ids, *impact.evidence_ids]
                ),
                "warnings": warnings,
                "errors": [],
                "details": {
                    "source_artifact_id": None,
                    "strategy_execution_supported": True,
                },
            }

        checks.append(
            _check(
                "source_checkpoint_exists",
                PASS,
                f"Resolved checkpoint artifact {checkpoint['artifact_id']}.",
            )
        )
        if checkpoint["artifact_type"] != "checkpoint":
            checks.append(
                _check(
                    "artifact_type",
                    FAIL,
                    "Selected artifact is not a checkpoint.",
                )
            )
        else:
            checks.append(_check("artifact_type", PASS, "Artifact is a checkpoint."))

        root = self.database.config.artifact_root
        absolute_path = resolve_artifact_path(root, checkpoint["artifact_path"])
        if not absolute_path.is_file():
            checks.append(
                _check(
                    "checkpoint_file",
                    FAIL,
                    "Checkpoint file is missing under the artifact root.",
                )
            )
        else:
            checks.append(
                _check("checkpoint_file", PASS, "Checkpoint file is present.")
            )
            if not checkpoint.get("artifact_hash"):
                checks.append(
                    _check(
                        "content_hash",
                        UNKNOWN,
                        "No registered content hash is available.",
                    )
                )
                lineage_gaps.append("checkpoint content hash is not recorded")
            else:
                try:
                    verify_file_hash(
                        root,
                        checkpoint["artifact_path"],
                        checkpoint["artifact_hash"],
                        max_bytes=self.database.config.max_artifact_bytes,
                    )
                    checks.append(
                        _check(
                            "content_hash",
                            PASS,
                            "Checkpoint content hash matches the registry.",
                        )
                    )
                except IntegrityFailure:
                    checks.append(
                        _check(
                            "content_hash",
                            FAIL,
                            "Checkpoint content hash does not match the registry.",
                        )
                    )

        classification = next(
            (
                entry
                for entry in impact.details.get("classifications", [])
                if entry.get("artifact_id") == checkpoint["artifact_id"]
            ),
            None,
        )
        if classification is None:
            checks.append(
                _check(
                    "exposure_classification",
                    UNKNOWN,
                    "Checkpoint has no exposure classification.",
                )
            )
            lineage_gaps.append("checkpoint exposure classification is unknown")
        elif classification["classification"] in {
            "confirmed_exposed",
            "potentially_affected",
        }:
            checks.append(
                _check(
                    "exposure_classification",
                    FAIL,
                    "Checkpoint includes or may include experience from the "
                    "affected interval.",
                )
            )
        elif classification["classification"] == (
            "not_exposed_based_on_recorded_lineage"
        ):
            checks.append(
                _check(
                    "exposure_classification",
                    PASS,
                    "Recorded lineage places the checkpoint outside the affected "
                    "interval.",
                )
            )
        else:
            checks.append(
                _check(
                    "exposure_classification",
                    UNKNOWN,
                    "Checkpoint exposure cannot be determined from recorded "
                    "lineage.",
                )
            )
            lineage_gaps.append("checkpoint exposure classification is incomplete")

        checkpoint_agent = checkpoint.get("agent_config_fingerprint")
        if target_agent_fingerprint and checkpoint_agent:
            if target_agent_fingerprint == checkpoint_agent:
                checks.append(
                    _check(
                        "algorithm_compatibility",
                        PASS,
                        "Agent configuration fingerprints match.",
                    )
                )
            else:
                checks.append(
                    _check(
                        "algorithm_compatibility",
                        FAIL,
                        "Agent configuration fingerprints differ.",
                    )
                )
        else:
            checks.append(
                _check(
                    "algorithm_compatibility",
                    UNKNOWN,
                    "Agent configuration fingerprint is missing on the checkpoint "
                    "or target.",
                )
            )
            lineage_gaps.append("agent configuration fingerprint is incomplete")

        checkpoint_environment = checkpoint.get("environment_version")
        if target_environment_version and checkpoint_environment:
            if target_environment_version == checkpoint_environment:
                checks.append(
                    _check(
                        "environment_compatibility",
                        PASS,
                        "Checkpoint and target environment versions match.",
                    )
                )
            else:
                checks.append(
                    _check(
                        "environment_compatibility",
                        UNKNOWN,
                        "Target environment version differs from the checkpoint; "
                        "compatibility has not been established.",
                    )
                )
                lineage_gaps.append("environment version compatibility is unresolved")
        else:
            checks.append(
                _check(
                    "environment_compatibility",
                    UNKNOWN,
                    "Checkpoint or target environment version is missing.",
                )
            )
            lineage_gaps.append("environment version is incomplete")

        components = set(checkpoint.get("included_state_components") or [])
        if "policy" in components:
            missing = [
                component
                for component in REQUIRED_CONTINUATION_COMPONENTS
                if component not in components
            ]
            if missing:
                warnings.append(
                    "Checkpoint does not record full continuation state ("
                    + ", ".join(missing)
                    + "); a restore would be a warm start, not a faithful "
                    "continuation."
                )
            checks.append(
                _check(
                    "state_components",
                    PASS,
                    "Policy state is present; recorded components: "
                    + (", ".join(sorted(components)) or "none"),
                )
            )
        elif components:
            checks.append(
                _check(
                    "state_components",
                    FAIL,
                    "Policy state is not recorded in the checkpoint metadata.",
                )
            )
        else:
            checks.append(
                _check(
                    "state_components",
                    UNKNOWN,
                    "Checkpoint state components are not recorded.",
                )
            )
            lineage_gaps.append("checkpoint state component metadata is missing")

        metadata = checkpoint.get("metadata") or {}
        serialization = metadata.get("serialization_format") or metadata.get("format")
        if serialization:
            checks.append(
                _check(
                    "serialization_compatibility",
                    PASS,
                    f"Recorded serialization format: {serialization}.",
                )
            )
        else:
            checks.append(
                _check(
                    "serialization_compatibility",
                    UNKNOWN,
                    "Serialization/library compatibility is not recorded.",
                )
            )
            lineage_gaps.append("serialization compatibility is unverified")

        observation_space = metadata.get("observation_space")
        action_space = metadata.get("action_space")
        if observation_space is not None and action_space is not None:
            checks.append(
                _check(
                    "space_compatibility",
                    PASS,
                    "Observation and action spaces are recorded on the checkpoint.",
                )
            )
        else:
            checks.append(
                _check(
                    "space_compatibility",
                    UNKNOWN,
                    "Observation/action space compatibility is not recorded.",
                )
            )
            lineage_gaps.append("observation/action space compatibility is unverified")

        if any(check.outcome.value == FAIL for check in checks):
            eligibility = RecoveryEligibility.ineligible
        elif any(
            check.outcome.value in {UNKNOWN, BLOCKED} for check in checks
        ):
            eligibility = RecoveryEligibility.needs_review
        else:
            eligibility = RecoveryEligibility.eligible

        if impact.impact_status.value == "unknown_incomplete_lineage":
            warnings.append(
                "Impact analysis is incomplete; checkpoint selection cannot rule "
                "out exposure with full confidence."
            )

        return {
            "recovery_eligibility": eligibility.value,
            "recovery_strategy": request.recovery_strategy.value,
            "recovery_reason": request.recovery_reason
            or (
                "Restore a checkpoint that recorded lineage places before the "
                "affected interval, then collect fresh experience."
            ),
            "source_checkpoint_id": checkpoint.get("checkpoint_id")
            or checkpoint["artifact_id"],
            "target_environment_version": target_environment_version,
            "target_agent_config_fingerprint": target_agent_fingerprint,
            "compatibility": [check.model_dump(mode="json") for check in checks],
            "lineage_gaps": unique_preserving_order(lineage_gaps),
            "evidence_ids": unique_preserving_order(
                [*request.evidence_ids, *impact.evidence_ids]
            ),
            "warnings": unique_preserving_order(warnings),
            "errors": [],
            "details": {
                "source_artifact_id": checkpoint["artifact_id"],
                "strategy_execution_supported": True,
                "impact_status": impact.impact_status.value,
            },
        }

    def create_assessment(
        self,
        incident_id: str,
        request: RecoveryAssessmentRequest,
        *,
        correlation_id: Optional[str] = None,
    ) -> RecoveryAssessment:
        if request.idempotency_key:
            with self.database.read() as conn:
                existing = recoveries_repo.get_assessment_by_idempotency(
                    conn, request.idempotency_key
                )
            if existing is not None:
                if existing["incident_id"] != incident_id:
                    raise RecoveryConflictError(
                        "Idempotency key was already used for another incident."
                    )
                return RecoveryAssessment.model_validate(existing)

        incident = self.provenance.get_incident(incident_id)
        impact = self.provenance.get_incident_impact(
            incident_id, correlation_id=correlation_id
        )
        with self.database.read() as conn:
            run = runs_repo.get_run(conn, incident.run_id)
            checkpoint = _resolve_checkpoint(conn, request.source_checkpoint_id)
        run_agent_fingerprint = run.get("agent_config_fingerprint") if run else None

        computed = self._build_assessment(
            incident=incident,
            impact=impact,
            run_agent_fingerprint=run_agent_fingerprint,
            checkpoint=checkpoint,
            request=request,
        )

        try:
            with self.database.write() as conn:
                created = recoveries_repo.create_assessment(
                    conn,
                    incident_id=incident_id,
                    idempotency_key=request.idempotency_key,
                    **computed,
                )
                audit_repo.append_audit(
                    conn,
                    entity_type="recovery_assessment",
                    entity_id=created["recovery_assessment_id"],
                    action="created",
                    status=created["recovery_eligibility"],
                    correlation_id=correlation_id,
                    details={
                        "incident_id": incident_id,
                        "strategy": created["recovery_strategy"],
                        "source_checkpoint_id": created["source_checkpoint_id"],
                    },
                )
        except sqlite3.IntegrityError as exc:
            if request.idempotency_key:
                with self.database.read() as conn:
                    existing = recoveries_repo.get_assessment_by_idempotency(
                        conn, request.idempotency_key
                    )
                if existing is not None and existing["incident_id"] == incident_id:
                    return RecoveryAssessment.model_validate(existing)
            raise RecoveryConflictError(
                "Recovery assessment conflicts with an existing record."
            ) from exc
        return RecoveryAssessment.model_validate(created)

    def get_assessment(
        self, incident_id: str, assessment_id: str
    ) -> RecoveryAssessment:
        with self.database.read() as conn:
            assessment = recoveries_repo.get_assessment(conn, assessment_id)
        if assessment is None or assessment["incident_id"] != incident_id:
            raise AssessmentNotFoundError(
                "Recovery assessment was not found for this incident.",
                details={"assessment_id": assessment_id, "incident_id": incident_id},
            )
        return RecoveryAssessment.model_validate(assessment)

    # ------------------------------------------------------------------
    # Recovery plan and execution
    # ------------------------------------------------------------------
    def _plan_actions(
        self,
        *,
        strategy: RecoveryStrategy,
        request: RecoveryCreateRequest,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = [
            {
                "action": "validate_recovery_preconditions",
                "status": "proposed",
                "detail": "Re-run preflight before any state change.",
            }
        ]
        if strategy is RecoveryStrategy.restore_checkpoint:
            actions.append(
                {
                    "action": "restore_checkpoint",
                    "status": "proposed",
                    "detail": "Restore the selected compatible checkpoint.",
                }
            )
        if request.discard_pending_rollouts:
            actions.append(
                {
                    "action": "discard_pending_rollouts",
                    "status": "proposed",
                    "detail": "Discard PPO on-policy data collected under the "
                    "faulty or incompatible environment state.",
                }
            )
        if request.collect_fresh_experience:
            actions.append(
                {
                    "action": "collect_fresh_experience",
                    "status": "proposed",
                    "detail": "Collect new experience under the corrected "
                    "environment before further updates.",
                }
            )
        actions.append(
            {
                "action": "run_post_recovery_evaluation",
                "status": "proposed",
                "detail": "Evaluate the recovered policy against a comparable "
                "baseline; execution completes before success is known.",
            }
        )
        return actions

    def create_recovery(
        self,
        incident_id: str,
        request: RecoveryCreateRequest,
        *,
        correlation_id: Optional[str] = None,
    ) -> Recovery:
        if request.idempotency_key:
            with self.database.read() as conn:
                existing = recoveries_repo.get_recovery_by_idempotency(
                    conn, request.idempotency_key
                )
            if existing is not None:
                if existing["incident_id"] != incident_id:
                    raise RecoveryConflictError(
                        "Idempotency key was already used for another incident."
                    )
                return Recovery.model_validate(existing)

        if request.assessment_id:
            assessment = self.get_assessment(incident_id, request.assessment_id)
        else:
            assessment = self.create_assessment(
                incident_id,
                RecoveryAssessmentRequest(
                    recovery_strategy=request.recovery_strategy
                    or RecoveryStrategy.restore_checkpoint,
                    source_checkpoint_id=request.source_checkpoint_id,
                    target_environment_version=request.target_environment_version,
                    target_agent_config_fingerprint=(
                        request.target_agent_config_fingerprint
                    ),
                    recovery_reason=request.recovery_reason,
                    discard_pending_rollouts=request.discard_pending_rollouts,
                    collect_fresh_experience=request.collect_fresh_experience,
                    evidence_ids=request.evidence_ids,
                    details=request.details,
                ),
                correlation_id=correlation_id,
            )

        strategy = (
            request.recovery_strategy
            or assessment.recovery_strategy
        )
        approval = request.approval or Approval()
        warnings = list(assessment.warnings)
        status = "proposed"
        failure_reason: Optional[str] = None
        if assessment.recovery_eligibility is RecoveryEligibility.ineligible:
            status = "blocked"
            failure_reason = (
                "Recovery is ineligible: preflight checks failed. "
                "No state was changed."
            )
        elif request.execute and not approval.approved:
            status = "blocked"
            failure_reason = (
                "Human approval is required before executing a recovery."
            )

        proposed_actions = self._plan_actions(strategy=strategy, request=request)
        preflight = {
            "eligibility": assessment.recovery_eligibility.value,
            "compatibility": [check.model_dump(mode="json") for check in assessment.compatibility],
            "lineage_gaps": assessment.lineage_gaps,
            "approval_required": True,
            "approved": approval.approved,
            "approved_by": approval.approved_by,
            "approved_at": (
                approval.approved_at.isoformat() if approval.approved_at else None
            ),
            "approval_note": approval.note,
        }
        evidence_ids = unique_preserving_order(
            [*request.evidence_ids, *assessment.evidence_ids]
        )
        details = {
            "source_artifact_id": assessment.details.get("source_artifact_id"),
            "strategy_execution_supported": assessment.details.get(
                "strategy_execution_supported", False
            ),
            "assessment_id": assessment.recovery_assessment_id,
        }

        try:
            with self.database.write() as conn:
                created = recoveries_repo.create_recovery(
                    conn,
                    incident_id=incident_id,
                    assessment_id=assessment.recovery_assessment_id,
                    recovery_status=status,
                    recovery_strategy=strategy.value,
                    recovery_reason=request.recovery_reason
                    or assessment.recovery_reason,
                    source_checkpoint_id=assessment.source_checkpoint_id,
                    target_environment_version=(
                        request.target_environment_version
                        or assessment.target_environment_version
                    ),
                    target_agent_config_fingerprint=(
                        request.target_agent_config_fingerprint
                        or assessment.target_agent_config_fingerprint
                    ),
                    proposed_actions=proposed_actions,
                    executed_actions=[],
                    preflight=preflight,
                    failure_reason=failure_reason,
                    evidence_ids=evidence_ids,
                    warnings=warnings,
                    errors=[],
                    details=details,
                    idempotency_key=request.idempotency_key,
                )
                audit_repo.append_audit(
                    conn,
                    entity_type="recovery",
                    entity_id=created["recovery_id"],
                    action="created",
                    status=created["recovery_status"],
                    correlation_id=correlation_id,
                    details={
                        "incident_id": incident_id,
                        "strategy": created["recovery_strategy"],
                        "source_checkpoint_id": created["source_checkpoint_id"],
                    },
                )
        except sqlite3.IntegrityError as exc:
            if request.idempotency_key:
                with self.database.read() as conn:
                    existing = recoveries_repo.get_recovery_by_idempotency(
                        conn, request.idempotency_key
                    )
                if existing is not None and existing["incident_id"] == incident_id:
                    return Recovery.model_validate(existing)
            raise RecoveryConflictError(
                "Recovery operation conflicts with an existing record."
            ) from exc

        if request.execute and created["recovery_status"] != "blocked":
            created = self._execute_recovery(
                created,
                assessment=assessment,
                request=request,
                correlation_id=correlation_id,
            )
        return Recovery.model_validate(created)

    def _executed_actions(
        self, base: list[dict[str, Any]], updates: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for action in base:
            name = action["action"]
            seen.add(name)
            patch = updates.get(name, {})
            result.append({**action, **patch})
        for name, patch in updates.items():
            if name not in seen:
                result.append({"action": name, **patch})
        return result

    def _update_recovery(
        self,
        recovery_id: str,
        *,
        correlation_id: Optional[str],
        action: str,
        status: str,
        **fields: Any,
    ) -> dict[str, Any]:
        with self.database.write() as conn:
            updated = recoveries_repo.update_recovery(
                conn, recovery_id, recovery_status=status, **fields
            )
            audit_repo.append_audit(
                conn,
                entity_type="recovery",
                entity_id=recovery_id,
                action=action,
                status=status,
                correlation_id=correlation_id,
                details={
                    "failure_reason": updated.get("failure_reason"),
                },
            )
            return updated

    def _execute_recovery(
        self,
        recovery: dict[str, Any],
        *,
        assessment: RecoveryAssessment,
        request: RecoveryCreateRequest,
        correlation_id: Optional[str],
    ) -> dict[str, Any]:
        recovery_id = recovery["recovery_id"]
        if recovery["recovery_strategy"] != RecoveryStrategy.restore_checkpoint.value:
            executed = self._executed_actions(
                recovery["proposed_actions"],
                {
                    "validate_recovery_preconditions": {
                        "status": "completed",
                        "detail": "Preflight passed; no state changed.",
                    },
                    "restore_checkpoint": {
                        "status": "skipped",
                        "detail": "Not part of the selected strategy.",
                    },
                    "run_post_recovery_evaluation": {
                        "status": "proposed",
                        "detail": "Recovery execution is required first.",
                    },
                },
            )
            return self._update_recovery(
                recovery_id,
                correlation_id=correlation_id,
                action="blocked",
                status="blocked",
                failure_reason=(
                    "Execution for this recovery strategy is not supported by "
                    "the MVP worker; the plan is recorded but no training state "
                    "was changed."
                ),
                executed_actions_json=dumps(executed),
            )

        source_identifier = recovery.get("source_checkpoint_id")
        with self.database.read() as conn:
            source = _resolve_checkpoint(conn, source_identifier)
        if source is None or source["artifact_type"] != "checkpoint":
            return self._update_recovery(
                recovery_id,
                correlation_id=correlation_id,
                action="blocked",
                status="blocked",
                failure_reason="Source checkpoint could not be resolved.",
            )

        incident = self.provenance.get_incident(recovery["incident_id"])
        lock_key = f"recovery:{incident.run_id}:{source['artifact_id']}"
        try:
            with self.database.write() as conn:
                owner = locks_repo.acquire_lock(
                    conn,
                    lock_key=lock_key,
                    ttl_seconds=300,
                )
        except OperationLockedError:
            executed = self._executed_actions(
                recovery["proposed_actions"],
                {
                    "validate_recovery_preconditions": {
                        "status": "blocked",
                        "detail": "Another recovery operation holds the lock.",
                    }
                },
            )
            return self._update_recovery(
                recovery_id,
                correlation_id=correlation_id,
                action="blocked",
                status="blocked",
                failure_reason=(
                    "Another recovery operation is already running for this "
                    "run and checkpoint."
                ),
                executed_actions_json=dumps(executed),
            )

        try:
            started_at = utc_now_iso()
            executing_actions = self._executed_actions(
                recovery["proposed_actions"],
                {
                    "validate_recovery_preconditions": {
                        "status": "completed",
                        "detail": "Preflight repeated at execution time.",
                        "started_at": started_at,
                        "completed_at": started_at,
                    }
                },
            )
            recovered = self._update_recovery(
                recovery_id,
                correlation_id=correlation_id,
                action="executing",
                status="executing",
                recovery_started_at=started_at,
                executed_actions_json=dumps(executing_actions),
            )

            root = self.database.config.artifact_root
            source_path = resolve_artifact_path(root, source["artifact_path"])
            if not source_path.is_file():
                raise IntegrityFailure("Source checkpoint file is missing.")
            expected_hash = source.get("artifact_hash")
            if expected_hash:
                verify_file_hash(
                    root,
                    source["artifact_path"],
                    expected_hash,
                    max_bytes=self.database.config.max_artifact_bytes,
                )

            destination_relative = (
                f"recovered/{recovery_id}/{source_path.name}"
            )
            destination_path = resolve_artifact_path(root, destination_relative)
            atomic_copy(source_path, destination_path)
            destination_hash = sha256_file(destination_path)
            if expected_hash and destination_hash != expected_hash:
                destination_path.unlink(missing_ok=True)
                raise IntegrityFailure(
                    "Recovered artifact hash does not match the source."
                )

            completed_at = utc_now_iso()
            new_artifact_id = new_id("artifact")
            new_checkpoint_id = new_id("checkpoint")
            with self.database.write() as conn:
                artifact = artifacts_repo.create_artifact(
                    conn,
                    artifact_id=new_artifact_id,
                    run_id=source["run_id"],
                    artifact_type="checkpoint",
                    artifact_path=destination_relative,
                    artifact_hash=destination_hash,
                    artifact_version=source.get("artifact_version"),
                    artifact_status="available",
                    integrity_status="verified",
                    parent_artifact_id=source["artifact_id"],
                    checkpoint_id=new_checkpoint_id,
                    checkpoint_path=destination_relative,
                    policy_version=source.get("policy_version"),
                    environment_id=source.get("environment_id"),
                    environment_version=(
                        recovery.get("target_environment_version")
                        or source.get("environment_version")
                    ),
                    agent_config_fingerprint=(
                        recovery.get("target_agent_config_fingerprint")
                        or source.get("agent_config_fingerprint")
                    ),
                    timestep=source.get("timestep"),
                    update_index=source.get("update_index"),
                    included_state_components=source.get(
                        "included_state_components"
                    ),
                    metadata_schema_version=source.get(
                        "metadata_schema_version", "1.0"
                    ),
                    metadata={
                        **(source.get("metadata") or {}),
                        "recovered_from": source["artifact_id"],
                        "recovery_id": recovery_id,
                    },
                )
                artifacts_repo.create_link(
                    conn,
                    run_id=source["run_id"],
                    from_artifact_id=source["artifact_id"],
                    to_artifact_id=new_artifact_id,
                    relation="recovered_as",
                )
                audit_repo.append_audit(
                    conn,
                    entity_type="artifact",
                    entity_id=new_artifact_id,
                    action="registered",
                    status="available",
                    correlation_id=correlation_id,
                    details={
                        "recovery_id": recovery_id,
                        "parent_artifact_id": source["artifact_id"],
                    },
                )

                executed = self._executed_actions(
                    recovery["proposed_actions"],
                    {
                        "validate_recovery_preconditions": {
                            "status": "completed",
                            "detail": "Hash and file checks passed at execution.",
                            "started_at": started_at,
                            "completed_at": started_at,
                        },
                        "restore_checkpoint": {
                            "status": "completed",
                            "detail": (
                                "Checkpoint copied atomically to a new recovered "
                                f"artifact {new_artifact_id}."
                            ),
                            "started_at": started_at,
                            "completed_at": completed_at,
                        },
                        "discard_pending_rollouts": {
                            "status": "skipped",
                            "detail": (
                                "Pending PPO rollout data must be discarded by the "
                                "training worker; no trainer is attached in this "
                                "process."
                            ),
                        },
                        "collect_fresh_experience": {
                            "status": "skipped",
                            "detail": (
                                "Fresh experience collection must be started by "
                                "Person 2's training worker."
                            ),
                        },
                        "run_post_recovery_evaluation": {
                            "status": "proposed",
                            "detail": (
                                "Evaluation has not run; recovery completion is "
                                "not recovery success."
                            ),
                        },
                    },
                )
                updated = recoveries_repo.update_recovery(
                    conn,
                    recovery_id,
                    recovery_status="completed",
                    recovery_completed_at=completed_at,
                    recovery_artifact_id=new_artifact_id,
                    recovered_checkpoint_id=new_checkpoint_id,
                    executed_actions_json=dumps(executed),
                    warnings_json=dumps(
                        unique_preserving_order(
                            [
                                *recovery.get("warnings", []),
                                "Recovery execution completed; recovery success "
                                "requires a post-recovery evaluation.",
                            ]
                        )
                    ),
                )
                audit_repo.append_audit(
                    conn,
                    entity_type="recovery",
                    entity_id=recovery_id,
                    action="completed",
                    status="completed",
                    correlation_id=correlation_id,
                    details={
                        "recovered_checkpoint_id": new_checkpoint_id,
                        "recovery_artifact_id": new_artifact_id,
                    },
                )
            return updated
        except Exception as exc:  # execution boundary: preserve failure state
            failure_message = (
                "Recovery execution failed or was blocked; the source checkpoint "
                "was not modified."
            )
            if isinstance(exc, IntegrityFailure):
                failure_message = (
                    "Recovery blocked: checkpoint integrity verification failed. "
                    "The source checkpoint was not modified."
                )
            try:
                failed_actions = self._executed_actions(
                    recovery["proposed_actions"],
                    {
                        "validate_recovery_preconditions": {
                            "status": "failed",
                            "detail": failure_message,
                        },
                        "restore_checkpoint": {
                            "status": "failed",
                            "detail": failure_message,
                        },
                    },
                )
                self._update_recovery(
                    recovery_id,
                    correlation_id=correlation_id,
                    action="failed",
                    status="failed",
                    failure_reason=failure_message,
                    executed_actions_json=dumps(failed_actions),
                )
            except Exception:
                pass
            with self.database.read() as conn:
                current = recoveries_repo.get_recovery(conn, recovery_id)
            return current or recovery
        finally:
            try:
                with self.database.write() as conn:
                    locks_repo.release_lock(
                        conn, lock_key=lock_key, owner_id=owner
                    )
            except Exception:
                pass

    def get_recovery(self, incident_id: str, recovery_id: str) -> Recovery:
        with self.database.read() as conn:
            recovery = recoveries_repo.get_recovery(conn, recovery_id)
        if recovery is None or recovery["incident_id"] != incident_id:
            raise RecoveryNotFoundError(
                "Recovery was not found for this incident.",
                details={"recovery_id": recovery_id, "incident_id": incident_id},
            )
        return Recovery.model_validate(recovery)
