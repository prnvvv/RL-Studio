"""Run-level policy evaluation: roll a *saved checkpoint* out in its own environment and persist the result.

This is the Person 4 evaluation made usable without client-supplied episodes. The incident/recovery acceptance record
(``EvaluationService``) is unchanged; this service produces the held-out episodes for it (``evaluate_recovery``) and
also records stand-alone evaluations of a run's checkpoint (``evaluate``). Rows are append-only: repeating an
evaluation never overwrites an earlier one, and no metric or baseline comparison is ever invented.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from backend.database.connection import Database
from backend.database.exceptions import IntegrityFailure, NotFoundError, ValidationError
from backend.database.paths import resolve_artifact_path, verify_file_hash
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import recoveries as recoveries_repo
from backend.database.repositories import runs as runs_repo
from backend.database.utils import dumps, loads, new_id, utc_now_iso
from backend.provenance.service import ProvenanceService
from backend.training_history import TrainingHistory

from . import rollout as rl
from .metrics import summarize_episodes
from .models import (
    AcceptanceCriteria,
    Evaluation,
    EvaluationCreateRequest,
)
from .service import EvaluationService

logger = logging.getLogger(__name__)

_JSON_COLUMNS = {
    "seeds_json": "seeds", "metrics_json": "metrics", "episodes_json": "episodes", "baseline_json": "baseline",
    "acceptance_json": "acceptance", "warnings_json": "warnings", "errors_json": "errors",
    "details_json": "details", "environment_config_json": "environment_config",
}

#: Stand-alone run evaluation criteria (all optional). Each configured criterion is checked against the measured value.
CRITERIA_KEYS = {"minimum_mean_reward", "minimum_success_rate", "maximum_timeout_rate"}


def _view(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    for column, name in _JSON_COLUMNS.items():
        fallback: Any = [] if name in {"seeds", "episodes", "warnings", "errors"} else ({} if name not in {"baseline", "acceptance"} else None)
        record[name] = loads(record.pop(column, None), fallback)
    return record


class RunEvaluationService:
    def __init__(self, database: Database, provenance: ProvenanceService | None = None) -> None:
        self.database = database
        self.history = TrainingHistory(database)
        self.provenance = provenance or ProvenanceService(database)
        self.legacy = EvaluationService(database)

    # ------------------------------------------------------------------ resolution
    def _run(self, run_id: str) -> dict[str, Any]:
        with self.database.read() as conn:
            run = runs_repo.get_run(conn, run_id)
        if run is None:
            raise NotFoundError("The run is not registered.", details={"run_id": run_id})
        return run

    def _checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            items = artifacts_repo.list_artifacts_for_run(conn, run_id)
        return [a for a in items if a["artifact_type"] == "checkpoint"]

    def _pick_checkpoint(self, run_id: str, identifier: str | None) -> dict[str, Any]:
        checkpoints = self._checkpoints(run_id)
        if identifier:
            for artifact in checkpoints:
                if identifier in (artifact["artifact_id"], artifact.get("checkpoint_id")):
                    return artifact
            raise NotFoundError("That checkpoint does not belong to this run.", details={"run_id": run_id, "checkpoint": identifier})
        if not checkpoints:
            raise ValidationError("This run has no registered checkpoint, so there is no saved policy to evaluate.",
                                  details={"run_id": run_id})
        return checkpoints[-1]  # ordered by timestep, then creation: the latest saved policy

    def _setup(self, run: dict[str, Any]) -> tuple[str | None, str | None, dict[str, Any], list[str]]:
        """(algorithm, environment id, environment params, warnings) for the run, from its recorded snapshots."""
        warnings: list[str] = []
        catalog = self.history.get_any(run["run_id"]) or {}
        snapshots = self.history.snapshots(run["run_id"])
        algorithm = catalog.get("algorithm") or (run.get("metadata") or {}).get("agent")
        env_id = (snapshots.get("environment") or {}).get("environment") or catalog.get("environment_name") or run.get("environment_id")
        params = dict((snapshots.get("environment") or {}).get("env_params") or {})
        if not snapshots:
            warnings.append("No recorded environment configuration snapshot exists for this run (a run from before "
                            "training history); the environment's default parameters were used.")
        return algorithm, env_id, params, warnings

    def _load(self, artifact: dict[str, Any], algorithm: str) -> Any:
        root = self.database.config.artifact_root
        if not artifact.get("artifact_hash"):
            raise rl.RolloutError("The checkpoint has no registered content hash, so its integrity cannot be verified.")
        try:
            verify_file_hash(root, artifact["artifact_path"], artifact["artifact_hash"],
                             max_bytes=self.database.config.max_artifact_bytes)
        except IntegrityFailure as exc:
            raise rl.RolloutError(f"The checkpoint failed integrity verification: {exc.message}") from exc
        except Exception as exc:
            raise rl.RolloutError("The checkpoint file could not be read.") from exc
        return rl.load_policy(resolve_artifact_path(root, artifact["artifact_path"]), algorithm)

    # ------------------------------------------------------------------ core
    def _play(self, run: dict[str, Any], artifact: dict[str, Any], *, episodes: int, base_seed: int) -> dict[str, Any]:
        """Roll the artifact out. Returns the identity, the episodes and the measured summary; raises ``RolloutError``."""
        algorithm, env_id, params, warnings = self._setup(run)
        if not algorithm:
            raise rl.RolloutError("The run's algorithm is not recorded, so its checkpoint cannot be loaded.")
        definition = rl.environment_definition(env_id)
        merged = {**rl.default_env_params(definition), **params}
        model = self._load(artifact, algorithm)
        seeds = [base_seed + i for i in range(episodes)]
        evaluated_version = rl.environment_version_of(definition, merged)
        recorded_version = artifact.get("environment_version") or run.get("environment_version")
        errors: list[str] = []
        if recorded_version and evaluated_version and recorded_version != evaluated_version:
            errors.append(f"The environment now reports version {evaluated_version!r} but the checkpoint was produced "
                          f"under {recorded_version!r}; the policy was not evaluated against a comparable environment.")
        if not recorded_version:
            warnings.append("The checkpoint's environment version is not recorded; comparability is unverified.")
        played = [] if errors else rl.rollout(model, algorithm=algorithm, definition=definition, env_params=merged, seeds=seeds)
        summary = summarize_episodes(played) if played else None
        return {
            "algorithm": algorithm, "environment_id": env_id, "environment_config": merged,
            "environment_version": evaluated_version or recorded_version, "seeds": seeds,
            "episodes": played, "summary": summary, "errors": errors, "warnings": warnings,
        }

    @staticmethod
    def _acceptance(criteria: dict[str, float] | None, summary: dict[str, Any]) -> dict[str, Any] | None:
        if not criteria:
            return None
        checks = []
        for key, threshold in criteria.items():
            measured = {"minimum_mean_reward": summary.get("mean_reward"), "minimum_success_rate": summary.get("success_rate"),
                        "maximum_timeout_rate": summary.get("timeout_rate")}[key]
            if measured is None:
                outcome = "unknown"
            elif key.startswith("minimum"):
                outcome = "pass" if measured >= threshold else "fail"
            else:
                outcome = "pass" if measured <= threshold else "fail"
            checks.append({"criterion": key, "threshold": threshold, "measured": measured, "outcome": outcome})
        outcomes = {c["outcome"] for c in checks}
        status = "failed" if "fail" in outcomes else "inconclusive" if "unknown" in outcomes else "passed"
        return {"status": status, "checks": checks}

    def _baseline(self, project_id: str | None, baseline_id: str | None, run_id: str, environment_version: str | None,
                  summary: dict[str, Any], seeds: list[int]) -> dict[str, Any] | None:
        if not baseline_id:
            return None
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM run_evaluations WHERE run_evaluation_id = ?", (baseline_id,)).fetchone()
        if row is None or row["project_id"] != project_id:
            raise NotFoundError("The baseline evaluation was not found in this project.", details={"baseline_evaluation_id": baseline_id})
        base = _view(row)
        identity = {"run_evaluation_id": base["run_evaluation_id"], "run_id": base["run_id"], "artifact_id": base["artifact_id"],
                    "policy_fingerprint": base["policy_fingerprint"], "environment_version": base["environment_version"],
                    "created_at": base["created_at"]}
        base_summary = (base["metrics"] or {}).get("summary") or {}
        if base["status"] in {"blocked", "failed"} or not base_summary or base_summary.get("valid_episode_count", 0) == 0:
            return {"identity": identity, "comparable": False, "reason": "The baseline evaluation produced no valid episodes.", "deltas": None}
        if base["environment_version"] != environment_version:
            return {"identity": identity, "comparable": False, "deltas": None,
                    "reason": f"Environment versions differ ({base['environment_version']!r} vs {environment_version!r})."}
        deltas = {}
        for key in ("mean_reward", "success_rate", "mean_episode_length", "timeout_rate"):
            left, right = summary.get(key), base_summary.get(key)
            deltas[key] = None if left is None or right is None else round(left - right, 6)
        return {"identity": identity, "comparable": True, "paired": sorted(base["seeds"]) == sorted(seeds), "deltas": deltas,
                "baseline_summary": {k: base_summary.get(k) for k in ("mean_reward", "success_rate", "mean_episode_length")}}

    def _persist(self, *, run: dict[str, Any], artifact: dict[str, Any], played: dict[str, Any] | None, status: str,
                 errors: list[str], warnings: list[str], seeds: list[int], baseline: dict[str, Any] | None,
                 acceptance: dict[str, Any] | None, incident_id: str | None, recovery_id: str | None, purpose: str,
                 episodes: int) -> dict[str, Any]:
        evaluation_id = new_id("reval")
        now = utc_now_iso()
        summary = (played or {}).get("summary")
        episode_rows = [e.model_dump() for e in (played or {}).get("episodes", [])]
        metrics = {"summary": summary, "variability": rl.variability((played or {}).get("episodes", [])) if played else None,
                   "definitions_ref": "backend/evaluation/metrics.py:METRIC_DEFINITIONS"}
        policy_fingerprint = artifact.get("artifact_hash")
        details = {"checkpoint_timestep": artifact.get("timestep"), "artifact_path": artifact.get("artifact_path"),
                   "deterministic_policy": True, "requested_episodes": episodes,
                   "fingerprint_note": "policy_fingerprint is the SHA-256 of the saved checkpoint file"}
        with self.database.write() as conn:
            conn.execute(
                """INSERT INTO run_evaluations(run_evaluation_id, project_id, run_id, artifact_id, checkpoint_id,
                   policy_fingerprint, agent_config_fingerprint, algorithm, environment_id, environment_version,
                   environment_config_json, status, episode_count, seeds_json, metrics_json, episodes_json, baseline_json,
                   acceptance_json, incident_id, recovery_id, purpose, warnings_json, errors_json, details_json,
                   created_at, completed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (evaluation_id, run.get("project_id"), run["run_id"], artifact["artifact_id"], artifact.get("checkpoint_id"),
                 policy_fingerprint, artifact.get("agent_config_fingerprint") or run.get("agent_config_fingerprint"),
                 (played or {}).get("algorithm"), (played or {}).get("environment_id") or run.get("environment_id"),
                 (played or {}).get("environment_version") or artifact.get("environment_version"),
                 dumps((played or {}).get("environment_config") or {}), status, len(episode_rows), dumps(seeds),
                 dumps(metrics), dumps(episode_rows), None if baseline is None else dumps(baseline),
                 None if acceptance is None else dumps(acceptance), incident_id, recovery_id, purpose,
                 dumps(warnings), dumps(errors), dumps(details), now, now),
            )
            row = conn.execute("SELECT * FROM run_evaluations WHERE run_evaluation_id = ?", (evaluation_id,)).fetchone()
        return _view(row)

    # ------------------------------------------------------------------ public API
    def evaluate(self, run_id: str, *, checkpoint_id: str | None = None, episodes: int = 20,
                 base_seed: int = rl.DEFAULT_BASE_SEED, baseline_evaluation_id: str | None = None,
                 criteria: dict[str, float] | None = None, incident_id: str | None = None,
                 recovery_id: str | None = None, purpose: str = "manual") -> dict[str, Any]:
        if not 1 <= episodes <= rl.MAX_EPISODES:
            raise ValidationError(f"episodes must be between 1 and {rl.MAX_EPISODES}.")
        unknown = set(criteria or {}) - CRITERIA_KEYS
        if unknown:
            raise ValidationError(f"Unknown acceptance criteria: {sorted(unknown)}.")
        run = self._run(run_id)
        artifact = self._pick_checkpoint(run_id, checkpoint_id)
        errors: list[str] = []
        warnings: list[str] = []
        played: dict[str, Any] | None = None
        try:
            played = self._play(run, artifact, episodes=episodes, base_seed=base_seed)
            errors, warnings = list(played["errors"]), list(played["warnings"])
        except rl.RolloutError as exc:
            errors.append(str(exc))
        summary = (played or {}).get("summary")
        if errors:
            status = "blocked"
        elif not summary or summary["valid_episode_count"] == 0:
            status = "inconclusive"
            errors.append("No episode completed without an error, so nothing can be measured.")
        else:
            status = "completed"
        if summary and summary["failed_episode_count"]:
            warnings.append(f"{summary['failed_episode_count']} of {summary['total_episode_count']} episodes raised an error and are excluded.")
        acceptance = self._acceptance(criteria, summary) if summary and status == "completed" else None
        if acceptance:
            status = acceptance["status"]
        baseline = self._baseline(run.get("project_id"), baseline_evaluation_id, run_id,
                                  (played or {}).get("environment_version"), summary, (played or {}).get("seeds", [])) if summary else None
        return self._persist(run=run, artifact=artifact, played=played, status=status, errors=errors, warnings=warnings,
                             seeds=(played or {}).get("seeds", []), baseline=baseline, acceptance=acceptance,
                             incident_id=incident_id, recovery_id=recovery_id, purpose=purpose, episodes=episodes)

    def get(self, run_id: str, evaluation_id: str) -> dict[str, Any]:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM run_evaluations WHERE run_evaluation_id = ? AND run_id = ?",
                               (evaluation_id, run_id)).fetchone()
        if row is None:
            raise NotFoundError("Evaluation was not found for this run.", details={"run_evaluation_id": evaluation_id})
        return _view(row)

    def list_for_run(self, run_id: str, *, include_episodes: bool = False) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM run_evaluations WHERE run_id = ? ORDER BY created_at DESC", (run_id,)).fetchall()
        return [self._slim(_view(r), include_episodes) for r in rows]

    def list_for_incident(self, incident_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM run_evaluations WHERE incident_id = ? ORDER BY created_at DESC", (incident_id,)).fetchall()
            legacy = conn.execute("SELECT evaluation_id FROM evaluations WHERE incident_id = ? ORDER BY created_at DESC",
                                  (incident_id,)).fetchall()
        return [self._slim(_view(r), False) for r in rows] + [{"legacy_evaluation_id": r["evaluation_id"]} for r in legacy]

    @staticmethod
    def _slim(record: dict[str, Any], include_episodes: bool) -> dict[str, Any]:
        if not include_episodes:
            record = {**record, "episodes": None}
        return record

    # ------------------------------------------------------------------ post-recovery
    def evaluate_recovery(self, incident_id: str, recovery_id: str, *, episodes: int = 20,
                          base_seed: int = rl.DEFAULT_BASE_SEED, criteria: AcceptanceCriteria | None = None,
                          correlation_id: str | None = None) -> dict[str, Any]:
        """Evaluate the policy a recovery actually produced, then record the Person 4 acceptance evaluation.

        The recovered policy is the recovery's own artifact (never the source checkpoint it was copied from). The
        healthy baseline is the checkpoint the recovery restored; the faulty reference, when it exists, is the run's
        latest earlier checkpoint that is neither of those. All three are rolled out on the same held-out seeds.
        """
        incident = self.provenance.get_incident(incident_id)
        with self.database.read() as conn:
            recovery = recoveries_repo.get_recovery(conn, recovery_id)
        if recovery is None or recovery["incident_id"] != incident_id:
            raise NotFoundError("Recovery was not found for this incident.", details={"recovery_id": recovery_id})
        if recovery["recovery_status"] not in {"completed", "evaluated"} or not recovery.get("recovery_artifact_id"):
            raise ValidationError("The recovery has not produced a recovered policy yet; execute it before evaluating.",
                                  details={"recovery_status": recovery["recovery_status"]})
        run = self._run(incident.run_id)
        recovered = self._pick_checkpoint(incident.run_id, recovery["recovery_artifact_id"])
        source = self._pick_checkpoint(incident.run_id, recovery.get("source_checkpoint_id"))
        faulty = next((a for a in reversed(self._checkpoints(incident.run_id))
                       if a["artifact_id"] not in {recovered["artifact_id"], source["artifact_id"]}
                       and (a.get("metadata") or {}).get("recovery_id") is None
                       and (a.get("timestep") or 0) >= (source.get("timestep") or 0)), None)
        seeds = [base_seed + i for i in range(episodes)]
        try:
            recovered_play = self._play(run, recovered, episodes=episodes, base_seed=base_seed)
            baseline_play = self._play(run, source, episodes=episodes, base_seed=base_seed)
            faulty_play = self._play(run, faulty, episodes=episodes, base_seed=base_seed) if faulty else None
        except rl.RolloutError as exc:
            raise ValidationError(f"The recovered policy could not be evaluated: {exc}") from exc
        for label, play in (("recovered", recovered_play), ("baseline", baseline_play), ("faulty", faulty_play)):
            if play is not None and play["errors"]:
                raise ValidationError(f"The {label} policy could not be evaluated: {'; '.join(play['errors'])}")
        # Record each rollout as its own immutable run-level evaluation, linked to the incident and recovery.
        recorded = {}
        for purpose, artifact, play in (("post_recovery", recovered, recovered_play), ("recovery_baseline", source, baseline_play),
                                        ("recovery_faulty", faulty, faulty_play)):
            if play is None:
                continue
            recorded[purpose] = self._persist(
                run=run, artifact=artifact, played=play, status="completed" if play["summary"] else "inconclusive",
                errors=[], warnings=play["warnings"], seeds=seeds, baseline=None, acceptance=None,
                incident_id=incident_id, recovery_id=recovery_id, purpose=purpose, episodes=episodes)
        request = EvaluationCreateRequest(
            recovery_id=recovery_id,
            baseline_run_id=incident.run_id, baseline_checkpoint_id=source["artifact_id"],
            recovered_run_id=incident.run_id, recovered_checkpoint_id=recovered["artifact_id"],
            faulty_run_id=incident.run_id if faulty else None, faulty_checkpoint_id=faulty["artifact_id"] if faulty else None,
            evaluation_environment_version=recovered_play["environment_version"] or "",
            # The rollouts above ran on the environment as it stands now and reported its version; a version
            # mismatch with the recorded checkpoint would have stopped the evaluation before this point.
            environment_healthy=True,
            baseline_episodes=baseline_play["episodes"], recovered_episodes=recovered_play["episodes"],
            faulty_episodes=faulty_play["episodes"] if faulty_play else [],
            acceptance_criteria=criteria or AcceptanceCriteria(),
            details={"source": "rollout", "run_evaluation_ids": {k: v["run_evaluation_id"] for k, v in recorded.items()}},
        )
        legacy: Evaluation = self.legacy.create_evaluation(incident_id, request, correlation_id=correlation_id)
        return {"evaluation": legacy.model_dump(mode="json"), "rollouts": {k: v["run_evaluation_id"] for k, v in recorded.items()},
                "recovered_policy": {"artifact_id": recovered["artifact_id"], "policy_fingerprint": recovered.get("artifact_hash")},
                "faulty_reference": None if faulty is None else faulty["artifact_id"],
                "note": None if faulty else "No earlier faulty checkpoint exists, so comparisons against the faulty policy are unavailable."}
