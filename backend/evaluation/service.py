from __future__ import annotations

import sqlite3
from typing import Any, Optional

from backend.database.connection import Database
from backend.database.exceptions import IntegrityFailure
from backend.database.paths import verify_file_hash
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import audit as audit_repo
from backend.database.repositories import evaluations as evaluations_repo
from backend.database.repositories import recoveries as recoveries_repo
from backend.database.repositories import runs as runs_repo
from backend.database.utils import (
    dumps,
    unique_preserving_order,
    utc_now_iso,
)
from backend.provenance.models import Incident
from backend.provenance.service import ProvenanceService

from .exceptions import (
    EvaluationConflictError,
    EvaluationNotFoundError,
    EvaluationValidationError,
)
from .metrics import (
    METRIC_DEFINITIONS,
    compare_groups,
    evaluate_acceptance,
    summarize_episodes,
)
from .models import (
    Evaluation,
    EvaluationCreateRequest,
    EvaluationStatus,
    EpisodeEvaluation,
)


def _seed_list(episodes: list[EpisodeEvaluation]) -> list[int]:
    return unique_preserving_order_int([episode.seed for episode in episodes])


def unique_preserving_order_int(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class EvaluationService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.provenance = ProvenanceService(database)

    # ------------------------------------------------------------------
    # Identity and linkage validation
    # ------------------------------------------------------------------
    def _load_identity(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        checkpoint_id: str,
        label: str,
        errors: list[str],
        warnings: list[str],
    ) -> dict[str, Any]:
        run = runs_repo.get_run(conn, run_id)
        if run is None:
            raise EvaluationValidationError(
                f"{label} run is not registered.",
                details={"run_id": run_id, "label": label},
            )
        artifact = artifacts_repo.get_artifact(conn, checkpoint_id)
        if artifact is None:
            artifact = artifacts_repo.get_artifact_by_checkpoint_id(
                conn, checkpoint_id
            )
        if artifact is None:
            raise EvaluationValidationError(
                f"{label} checkpoint is not registered.",
                details={"checkpoint_id": checkpoint_id, "label": label},
            )
        if artifact["artifact_type"] != "checkpoint":
            raise EvaluationValidationError(
                f"{label} artifact is not a checkpoint.",
                details={"artifact_id": artifact["artifact_id"], "label": label},
            )
        if artifact["run_id"] != run_id:
            raise EvaluationValidationError(
                f"{label} checkpoint does not belong to the supplied run.",
                details={
                    "run_id": run_id,
                    "artifact_id": artifact["artifact_id"],
                    "label": label,
                },
            )

        if artifact["artifact_status"] != "available":
            errors.append(
                f"{label} checkpoint artifact status is "
                f"{artifact['artifact_status']}, not available."
            )
        if artifact["integrity_status"] != "verified":
            errors.append(
                f"{label} checkpoint integrity status is "
                f"{artifact['integrity_status']}, not verified."
            )
        if not artifact.get("artifact_hash"):
            errors.append(f"{label} checkpoint has no registered content hash.")
        else:
            try:
                verify_file_hash(
                    self.database.config.artifact_root,
                    artifact["artifact_path"],
                    artifact["artifact_hash"],
                    max_bytes=self.database.config.max_artifact_bytes,
                )
            except IntegrityFailure as exc:
                errors.append(
                    f"{label} checkpoint failed integrity verification: {exc.message}"
                )
            except Exception:
                errors.append(
                    f"{label} checkpoint file could not be read or verified."
                )

        policy_fingerprint = (
            artifact.get("agent_config_fingerprint")
            or run.get("agent_config_fingerprint")
        )
        if not policy_fingerprint:
            warnings.append(
                f"{label} policy fingerprint is not recorded; exact policy identity "
                "is incomplete."
            )
        environment_version = (
            artifact.get("environment_version")
            or run.get("environment_version")
        )
        if not environment_version:
            warnings.append(
                f"{label} checkpoint environment version is not recorded."
            )
        return {
            "run_id": run_id,
            "artifact_id": artifact["artifact_id"],
            "checkpoint_id": artifact.get("checkpoint_id") or artifact["artifact_id"],
            "policy_fingerprint": policy_fingerprint,
            "agent_config_fingerprint": artifact.get("agent_config_fingerprint")
            or run.get("agent_config_fingerprint"),
            "environment_id": artifact.get("environment_id")
            or run.get("environment_id"),
            "environment_version": environment_version,
            "artifact_hash": artifact.get("artifact_hash"),
            "timestep": artifact.get("timestep"),
        }

    def _load_recovery(
        self,
        conn: sqlite3.Connection,
        *,
        incident: Incident,
        request: EvaluationCreateRequest,
        recovered_identity: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> Optional[dict[str, Any]]:
        if not request.recovery_id:
            warnings.append(
                "Evaluation is not linked to a recovery; recovery_verified remains false."
            )
            return None
        recovery = recoveries_repo.get_recovery(conn, request.recovery_id)
        if recovery is None or recovery["incident_id"] != incident.incident_id:
            raise EvaluationNotFoundError(
                "Recovery was not found for this incident.",
                details={
                    "recovery_id": request.recovery_id,
                    "incident_id": incident.incident_id,
                },
            )
        if recovery["recovery_status"] not in {"completed", "evaluated"}:
            errors.append(
                "Recovery execution is not complete; evaluation cannot verify "
                f"recovery from status {recovery['recovery_status']}."
            )
        if not recovery.get("recovery_artifact_id"):
            errors.append("Recovery has no recovered artifact to evaluate.")
        elif recovery["recovery_artifact_id"] != recovered_identity["artifact_id"]:
            errors.append(
                "The evaluated checkpoint is not the artifact produced by the "
                "linked recovery."
            )
        if (
            recovery.get("recovered_checkpoint_id")
            and recovery["recovered_checkpoint_id"]
            != recovered_identity["checkpoint_id"]
        ):
            errors.append(
                "The evaluated checkpoint ID does not match the linked recovery."
            )
        target_environment = recovery.get("target_environment_version")
        if target_environment:
            if request.evaluation_environment_version != target_environment:
                errors.append(
                    "Evaluation environment version differs from the recovery "
                    "target environment."
                )
            if (
                recovered_identity.get("environment_version")
                and recovered_identity["environment_version"] != target_environment
            ):
                errors.append(
                    "The evaluated checkpoint environment version differs from "
                    "the recovery target environment."
                )
        else:
            warnings.append(
                "Recovery target environment version is not recorded; evaluation "
                "environment comparability is uncertain."
            )
        target_agent = recovery.get("target_agent_config_fingerprint")
        if (
            target_agent
            and recovered_identity.get("agent_config_fingerprint")
            and target_agent != recovered_identity["agent_config_fingerprint"]
        ):
            errors.append(
                "The evaluated checkpoint agent configuration does not match "
                "the recovery target agent configuration."
            )
        return recovery

    # ------------------------------------------------------------------
    # Creation and retrieval
    # ------------------------------------------------------------------
    def create_evaluation(
        self,
        incident_id: str,
        request: EvaluationCreateRequest,
        *,
        correlation_id: Optional[str] = None,
    ) -> Evaluation:
        if request.idempotency_key:
            with self.database.read() as conn:
                existing = evaluations_repo.get_evaluation_by_idempotency(
                    conn, request.idempotency_key
                )
            if existing is not None:
                if existing["incident_id"] != incident_id:
                    raise EvaluationConflictError(
                        "Idempotency key was already used for another incident."
                    )
                return Evaluation.model_validate(existing)

        incident = self.provenance.get_incident(incident_id)
        errors: list[str] = []
        warnings: list[str] = []

        with self.database.read() as conn:
            baseline_identity = self._load_identity(
                conn,
                run_id=request.baseline_run_id,
                checkpoint_id=request.baseline_checkpoint_id,
                label="Healthy baseline",
                errors=errors,
                warnings=warnings,
            )
            recovered_identity = self._load_identity(
                conn,
                run_id=request.recovered_run_id,
                checkpoint_id=request.recovered_checkpoint_id,
                label="Recovered",
                errors=errors,
                warnings=warnings,
            )
            faulty_identity = (
                self._load_identity(
                    conn,
                    run_id=request.faulty_run_id,
                    checkpoint_id=request.faulty_checkpoint_id,
                    label="Faulty baseline",
                    errors=errors,
                    warnings=warnings,
                )
                if request.faulty_run_id and request.faulty_checkpoint_id
                else None
            )
            recovery = self._load_recovery(
                conn,
                incident=incident,
                request=request,
                recovered_identity=recovered_identity,
                errors=errors,
                warnings=warnings,
            )

        if not request.environment_healthy:
            errors.append(
                "Evaluation environment is not confirmed healthy; evaluation "
                "cannot be used to verify recovery."
            )

        seeds = _seed_list(request.recovered_episodes)
        if len(seeds) != len(request.recovered_episodes):
            warnings.append(
                "Recovered evaluation contains duplicate seeds; seed uniqueness "
                "is not guaranteed."
            )
        baseline_seeds = _seed_list(request.baseline_episodes)
        if len(baseline_seeds) != len(request.baseline_episodes):
            warnings.append(
                "Healthy baseline contains duplicate seeds; paired comparison is "
                "not available."
            )
        if len(request.baseline_episodes) != len(request.recovered_episodes):
            warnings.append(
                "Healthy baseline and recovered episode counts differ; this is "
                "not a paired comparison."
            )
        elif set(baseline_seeds) != set(seeds):
            warnings.append(
                "Healthy baseline and recovered seeds differ; paired comparison "
                "is not available."
            )
        if not request.faulty_episodes:
            warnings.append(
                "No faulty-baseline episodes were supplied; comparisons and "
                "acceptance criteria against the faulty policy are unavailable."
            )
        if incident.environment_version and (
            incident.environment_version != request.evaluation_environment_version
        ) and not recovery:
            warnings.append(
                "Evaluation environment differs from the incident environment "
                "and no recovery target was supplied."
            )

        baseline_summary = summarize_episodes(request.baseline_episodes)
        recovered_summary = summarize_episodes(request.recovered_episodes)
        faulty_summary = (
            summarize_episodes(request.faulty_episodes)
            if request.faulty_episodes
            else None
        )
        comparisons = compare_groups(
            baseline=baseline_summary,
            recovered=recovered_summary,
            faulty=faulty_summary,
            baseline_episodes=request.baseline_episodes,
            recovered_episodes=request.recovered_episodes,
        )

        if errors:
            status = EvaluationStatus.blocked
            errors.append("Evaluation was blocked; no recovery success is claimed.")
            acceptance: dict[str, Any] = {
                "status": "blocked",
                "reason": "Blocking preconditions were not met.",
                "checks": [],
                "configured": False,
            }
        elif (
            baseline_summary["valid_episode_count"] == 0
            or recovered_summary["valid_episode_count"] == 0
        ):
            status = EvaluationStatus.inconclusive
            errors.append(
                "Healthy baseline or recovered evaluation produced no valid "
                "episodes, so performance cannot be compared."
            )
            acceptance = {
                "status": "inconclusive",
                "reason": "No valid episodes are available for comparison.",
                "checks": [],
                "configured": False,
            }
        else:
            acceptance = evaluate_acceptance(
                criteria=request.acceptance_criteria,
                baseline=baseline_summary,
                faulty=faulty_summary,
                recovered=recovered_summary,
            )
            status = EvaluationStatus(acceptance["status"])

        recovery_verified = bool(
            recovery is not None and status is EvaluationStatus.passed
        )
        recovery_verification_status = (
            status if recovery is not None else EvaluationStatus.not_run
        )

        reward_improvement = None
        if (
            recovered_summary["mean_reward"] is not None
            and baseline_summary["mean_reward"] is not None
        ):
            reward_improvement = round(
                recovered_summary["mean_reward"]
                - baseline_summary["mean_reward"],
                6,
            )
        success_rate_improvement = None
        if (
            recovered_summary["success_rate"] is not None
            and baseline_summary["success_rate"] is not None
        ):
            success_rate_improvement = round(
                recovered_summary["success_rate"]
                - baseline_summary["success_rate"],
                6,
            )

        if status is EvaluationStatus.blocked:
            warnings.append(
                "Blocked evaluation records no recovery success; resolve the "
                "listed errors and submit a new evaluation."
            )
        elif status is EvaluationStatus.inconclusive:
            warnings.append(
                "Inconclusive evaluation does not verify recovery; add acceptance "
                "criteria, valid episodes, or comparable baselines."
            )
            warnings.append(acceptance["reason"])
        elif status is EvaluationStatus.failed:
            warnings.append(
                "Evaluation did not meet the configured acceptance criteria; "
                "recovery is not verified."
            )
            warnings.append(acceptance["reason"])

        details = {
            "identities": {
                "healthy_baseline": baseline_identity,
                "faulty_baseline": faulty_identity,
                "recovered": recovered_identity,
            },
            "evaluation_config": {
                "environment_version": request.evaluation_environment_version,
                "environment_healthy": request.environment_healthy,
                "episode_count": len(request.recovered_episodes),
                "baseline_episode_count": len(request.baseline_episodes),
                "faulty_episode_count": len(request.faulty_episodes),
                "seeds": seeds,
                "baseline_seeds": baseline_seeds,
                "paired_comparison": comparisons[
                    "paired_recovered_vs_healthy_baseline"
                ]
                is not None,
            },
            "metric_definitions": METRIC_DEFINITIONS,
            "acceptance_results": acceptance,
            "recovery_link": (
                {
                    "recovery_id": recovery["recovery_id"],
                    "recovery_status": recovery["recovery_status"],
                    "recovery_artifact_id": recovery.get("recovery_artifact_id"),
                    "recovered_checkpoint_id": recovery.get(
                        "recovered_checkpoint_id"
                    ),
                    "target_environment_version": recovery.get(
                        "target_environment_version"
                    ),
                    "target_agent_config_fingerprint": recovery.get(
                        "target_agent_config_fingerprint"
                    ),
                }
                if recovery
                else None
            ),
            "request_details": request.details,
        }
        metrics = {
            "healthy_baseline": baseline_summary,
            "faulty_baseline": faulty_summary,
            "recovered": recovered_summary,
            "definitions": METRIC_DEFINITIONS,
        }
        completed_at = utc_now_iso()
        evidence_ids = unique_preserving_order(
            [
                *request.evidence_ids,
                *((recovery or {}).get("evidence_ids") or []),
            ]
        )
        deduped_warnings = unique_preserving_order(warnings)
        deduped_errors = unique_preserving_order(errors)

        try:
            with self.database.write() as conn:
                created = evaluations_repo.create_evaluation(
                    conn,
                    incident_id=incident_id,
                    recovery_id=request.recovery_id,
                    baseline_run_id=request.baseline_run_id,
                    recovered_run_id=request.recovered_run_id,
                    evaluation_status=status.value,
                    evaluation_environment_version=(
                        request.evaluation_environment_version
                    ),
                    baseline_mean_reward=baseline_summary["mean_reward"],
                    recovered_mean_reward=recovered_summary["mean_reward"],
                    baseline_success_rate=baseline_summary["success_rate"],
                    recovered_success_rate=recovered_summary["success_rate"],
                    baseline_episode_length=baseline_summary[
                        "mean_episode_length"
                    ],
                    recovered_episode_length=recovered_summary[
                        "mean_episode_length"
                    ],
                    reward_improvement=reward_improvement,
                    success_rate_improvement=success_rate_improvement,
                    evaluation_metrics=metrics,
                    comparison_results=comparisons,
                    acceptance_criteria=request.acceptance_criteria.model_dump(
                        exclude_none=True
                    ),
                    recovery_verification_status=(
                        recovery_verification_status.value
                    ),
                    recovery_verified=recovery_verified,
                    episode_count=len(request.recovered_episodes),
                    seeds=seeds,
                    evidence_ids=evidence_ids,
                    warnings=deduped_warnings,
                    errors=deduped_errors,
                    details=details,
                    idempotency_key=request.idempotency_key,
                    completed_at=completed_at,
                )
                audit_repo.append_audit(
                    conn,
                    entity_type="evaluation",
                    entity_id=created["evaluation_id"],
                    action="created",
                    status=created["evaluation_status"],
                    correlation_id=correlation_id,
                    details={
                        "incident_id": incident_id,
                        "recovery_id": request.recovery_id,
                        "recovery_verified": recovery_verified,
                        "environment_version": request.evaluation_environment_version,
                    },
                )
                if (
                    recovery is not None
                    and status
                    in {
                        EvaluationStatus.passed,
                        EvaluationStatus.failed,
                        EvaluationStatus.inconclusive,
                    }
                ):
                    current_recovery = recoveries_repo.get_recovery(
                        conn, recovery["recovery_id"]
                    )
                    if current_recovery and current_recovery[
                        "recovery_status"
                    ] in {"completed", "evaluated"}:
                        recovery_details = {
                            **(current_recovery.get("details") or {}),
                            "evaluation_id": created["evaluation_id"],
                            "evaluation_status": created["evaluation_status"],
                            "recovery_verified": recovery_verified,
                            "evaluation_environment_version": (
                                request.evaluation_environment_version
                            ),
                            "last_evaluated_at": completed_at,
                        }
                        recoveries_repo.update_recovery(
                            conn,
                            recovery["recovery_id"],
                            recovery_status="evaluated",
                            details_json=dumps(recovery_details),
                        )
                        audit_repo.append_audit(
                            conn,
                            entity_type="recovery",
                            entity_id=recovery["recovery_id"],
                            action="evaluated",
                            status="evaluated",
                            correlation_id=correlation_id,
                            details={
                                "evaluation_id": created["evaluation_id"],
                                "evaluation_status": created[
                                    "evaluation_status"
                                ],
                                "recovery_verified": recovery_verified,
                            },
                        )
        except sqlite3.IntegrityError as exc:
            if request.idempotency_key:
                with self.database.read() as conn:
                    existing = evaluations_repo.get_evaluation_by_idempotency(
                        conn, request.idempotency_key
                    )
                if existing is not None and existing["incident_id"] == incident_id:
                    return Evaluation.model_validate(existing)
            raise EvaluationConflictError(
                "Evaluation conflicts with an existing record."
            ) from exc

        return Evaluation.model_validate(created)

    def get_evaluation(
        self, incident_id: str, evaluation_id: str
    ) -> Evaluation:
        with self.database.read() as conn:
            evaluation = evaluations_repo.get_evaluation(conn, evaluation_id)
        if evaluation is None or evaluation["incident_id"] != incident_id:
            raise EvaluationNotFoundError(
                "Evaluation was not found for this incident.",
                details={
                    "evaluation_id": evaluation_id,
                    "incident_id": incident_id,
                },
            )
        return Evaluation.model_validate(evaluation)
