from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.evaluation.exceptions import (
    EvaluationNotFoundError,
    EvaluationValidationError,
)
from backend.evaluation.metrics import evaluate_acceptance, summarize_episodes
from backend.evaluation.models import (
    AcceptanceCriteria,
    EpisodeEvaluation,
    EvaluationCreateRequest,
    EvaluationStatus,
)
from backend.evaluation.service import EvaluationService
from backend.provenance.models import (
    ArtifactRegistration,
    IncidentRegistration,
    RunRegistration,
)
from backend.provenance.service import ProvenanceService
from backend.recovery.models import (
    Approval,
    Recovery,
    RecoveryAssessmentRequest,
    RecoveryCreateRequest,
)
from backend.recovery.service import RecoveryService


class EvaluationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = DatabaseConfig.for_tests(Path(self.tempdir.name))
        self.db = Database(self.config)
        self.db.initialize()
        self.provenance = ProvenanceService(self.db)
        self.recovery_service = RecoveryService(self.db)
        self.service = EvaluationService(self.db)
        for run_id in ("run_1", "run_baseline"):
            self.provenance.register_run(
                RunRegistration(
                    run_id=run_id,
                    environment_id="warehouse",
                    environment_version="warehouse_v1",
                    agent_config_fingerprint="ppo-abc",
                )
            )
        self._write("run_1/cp_10.zip", b"checkpoint-10")
        self._write("run_1/cp_80.zip", b"checkpoint-80")
        self._write("run_baseline/cp_10.zip", b"baseline-checkpoint-10")
        self.provenance.register_artifact(
            ArtifactRegistration(
                artifact_id="artifact_cp_10",
                run_id="run_1",
                artifact_type="checkpoint",
                artifact_path="run_1/cp_10.zip",
                checkpoint_id="checkpoint_10",
                timestep=10,
                included_state_components=["policy", "optimizer", "rng", "counters"],
                metadata={
                    "serialization_format": "zip",
                    "observation_space": [4],
                    "action_space": [4],
                },
            )
        )
        self.provenance.register_artifact(
            ArtifactRegistration(
                artifact_id="artifact_cp_80",
                run_id="run_1",
                artifact_type="checkpoint",
                artifact_path="run_1/cp_80.zip",
                checkpoint_id="checkpoint_80",
                timestep=80,
                included_state_components=["policy", "optimizer", "rng", "counters"],
                metadata={
                    "serialization_format": "zip",
                    "observation_space": [4],
                    "action_space": [4],
                },
            )
        )
        self.provenance.register_artifact(
            ArtifactRegistration(
                artifact_id="artifact_baseline_cp_10",
                run_id="run_baseline",
                artifact_type="checkpoint",
                artifact_path="run_baseline/cp_10.zip",
                checkpoint_id="baseline_checkpoint_10",
                timestep=10,
                included_state_components=["policy", "optimizer", "rng", "counters"],
                metadata={
                    "serialization_format": "zip",
                    "observation_space": [4],
                    "action_space": [4],
                },
            )
        )
        self.provenance.register_incident(
            IncidentRegistration(
                incident_id="incident_1",
                run_id="run_1",
                verification_id="verification_1",
                requirement_id="requirement_1",
                environment_id="warehouse",
                environment_version="warehouse_v1",
                source_environment_version="warehouse_v1",
                corruption_start_timestep=40,
                corruption_end_timestep=60,
                evidence_ids=["evidence_1"],
            )
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write(self, relative: str, content: bytes) -> None:
        path = self.config.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _episodes(
        self,
        *,
        successes: list[bool],
        rewards: list[float],
        lengths: list[int] | None = None,
        errors: list[str | None] | None = None,
        base_seed: int = 1,
        collisions: list[bool] | None = None,
        timeouts: list[bool] | None = None,
    ) -> list[EpisodeEvaluation]:
        lengths = lengths or [50 for _ in successes]
        errors = errors or [None for _ in successes]
        collisions = collisions or [False for _ in successes]
        timeouts = timeouts or [False for _ in successes]
        return [
            EpisodeEvaluation(
                episode_id=f"episode_{base_seed + index}",
                seed=base_seed + index,
                reward=rewards[index],
                episode_length=lengths[index],
                success=successes[index],
                collision=collisions[index],
                timed_out=timeouts[index],
                error=errors[index],
            )
            for index in range(len(successes))
        ]

    def _completed_recovery(self) -> Recovery:
        assessment = self.recovery_service.create_assessment(
            "incident_1",
            RecoveryAssessmentRequest(
                source_checkpoint_id="checkpoint_10",
                target_environment_version="warehouse_v1",
                target_agent_config_fingerprint="ppo-abc",
            ),
        )
        return self.recovery_service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
                execute=True,
                approval=Approval(approved=True, approved_by="operator_1"),
            ),
        )

    def _request(
        self,
        recovery: Recovery | None,
        **overrides,
    ) -> EvaluationCreateRequest:
        recovered_checkpoint = (
            recovery.recovered_checkpoint_id
            if recovery is not None and recovery.recovered_checkpoint_id
            else "checkpoint_10"
        )
        values = {
            "recovery_id": recovery.recovery_id if recovery is not None else None,
            "baseline_run_id": "run_baseline",
            "baseline_checkpoint_id": "baseline_checkpoint_10",
            "recovered_run_id": "run_1",
            "recovered_checkpoint_id": recovered_checkpoint,
            "faulty_run_id": "run_1",
            "faulty_checkpoint_id": "checkpoint_80",
            "evaluation_environment_version": "warehouse_v1",
            "environment_healthy": True,
            "baseline_episodes": self._episodes(
                successes=[True, True, True, True],
                rewards=[100.0, 100.0, 100.0, 100.0],
            ),
            "recovered_episodes": self._episodes(
                successes=[True, True, True, True],
                rewards=[95.0, 95.0, 95.0, 95.0],
            ),
            "faulty_episodes": self._episodes(
                successes=[False, False, True, False],
                rewards=[10.0, 10.0, 10.0, 10.0],
            ),
            "acceptance_criteria": AcceptanceCriteria(
                minimum_recovered_success_rate=0.75,
                minimum_success_rate_improvement_vs_faulty=0.5,
                maximum_success_rate_regression_vs_healthy=0.0,
                minimum_mean_reward_improvement_vs_faulty=50.0,
                maximum_mean_reward_regression_vs_healthy=10.0,
                maximum_collision_rate=0.0,
                maximum_timeout_rate=0.0,
                minimum_valid_episodes_per_group=4,
                require_no_episode_errors=True,
            ),
        }
        values.update(overrides)
        return EvaluationCreateRequest(**values)

    def test_metric_summary_excludes_infrastructure_errors(self) -> None:
        episodes = self._episodes(
            successes=[True, False, True],
            rewards=[10.0, 20.0, 40.0],
            errors=[None, None, "environment crashed"],
        )

        summary = summarize_episodes(episodes)

        self.assertEqual(summary["total_episode_count"], 3)
        self.assertEqual(summary["valid_episode_count"], 2)
        self.assertEqual(summary["failed_episode_count"], 1)
        self.assertEqual(summary["success_rate"], 0.5)
        self.assertEqual(summary["mean_reward"], 15.0)
        interval = summary["confidence_intervals"]["success_rate"]
        self.assertIsNotNone(interval)
        self.assertLessEqual(interval["lower"], 0.5)
        self.assertGreaterEqual(interval["upper"], 0.5)

    def test_acceptance_passes_and_verifies_completed_recovery(self) -> None:
        recovery = self._completed_recovery()

        evaluation = self.service.create_evaluation(
            "incident_1", self._request(recovery)
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.passed)
        self.assertTrue(evaluation.recovery_verified)
        self.assertEqual(
            evaluation.recovery_verification_status, EvaluationStatus.passed
        )
        self.assertEqual(evaluation.recovery_id, recovery.recovery_id)
        self.assertEqual(evaluation.episode_count, 4)
        self.assertEqual(evaluation.seeds, [1, 2, 3, 4])
        self.assertEqual(evaluation.baseline_success_rate, 1.0)
        self.assertEqual(evaluation.recovered_success_rate, 1.0)
        self.assertEqual(evaluation.reward_improvement, -5.0)
        self.assertEqual(evaluation.success_rate_improvement, 0.0)
        self.assertEqual(
            evaluation.comparison_results["recovered_minus_faulty"][
                "mean_reward"
            ],
            85.0,
        )
        self.assertIsNotNone(
            evaluation.comparison_results["paired_recovered_vs_healthy_baseline"]
        )
        self.assertEqual(
            evaluation.details["acceptance_results"]["status"], "passed"
        )
        self.assertEqual(
            evaluation.details["identities"]["recovered"]["checkpoint_id"],
            recovery.recovered_checkpoint_id,
        )
        self.assertIn("evidence_1", evaluation.evidence_ids)

        loaded_recovery = self.recovery_service.get_recovery(
            "incident_1", recovery.recovery_id
        )
        self.assertEqual(loaded_recovery.recovery_status.value, "evaluated")
        self.assertEqual(
            loaded_recovery.details["evaluation_id"], evaluation.evaluation_id
        )
        self.assertTrue(loaded_recovery.details["recovery_verified"])

    def test_acceptance_failure_marks_recovery_evaluated_not_verified(self) -> None:
        recovery = self._completed_recovery()
        request = self._request(
            recovery,
            acceptance_criteria=AcceptanceCriteria(
                minimum_recovered_success_rate=1.0
            ),
            recovered_episodes=self._episodes(
                successes=[True, True, True, False],
                rewards=[95.0, 95.0, 95.0, 30.0],
            ),
        )

        evaluation = self.service.create_evaluation("incident_1", request)

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.failed)
        self.assertFalse(evaluation.recovery_verified)
        self.assertEqual(
            evaluation.recovery_verification_status, EvaluationStatus.failed
        )
        check = evaluation.details["acceptance_results"]["checks"][0]
        self.assertFalse(check["passed"])
        self.assertEqual(
            self.recovery_service.get_recovery(
                "incident_1", recovery.recovery_id
            ).recovery_status.value,
            "evaluated",
        )

    def test_no_criteria_is_inconclusive_not_verified(self) -> None:
        recovery = self._completed_recovery()

        evaluation = self.service.create_evaluation(
            "incident_1",
            self._request(recovery, acceptance_criteria=AcceptanceCriteria()),
        )

        self.assertEqual(
            evaluation.evaluation_status, EvaluationStatus.inconclusive
        )
        self.assertFalse(evaluation.recovery_verified)
        self.assertFalse(
            evaluation.details["acceptance_results"]["configured"]
        )
        self.assertTrue(any("No acceptance criteria" in warning for warning in evaluation.warnings))

    def test_incomplete_recovery_blocks_evaluation(self) -> None:
        assessment = self.recovery_service.create_assessment(
            "incident_1",
            RecoveryAssessmentRequest(
                source_checkpoint_id="checkpoint_10",
                target_environment_version="warehouse_v1",
                target_agent_config_fingerprint="ppo-abc",
            ),
        )
        recovery = self.recovery_service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
                execute=False,
            ),
        )

        evaluation = self.service.create_evaluation(
            "incident_1", self._request(recovery)
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.blocked)
        self.assertFalse(evaluation.recovery_verified)
        self.assertTrue(
            any("not complete" in error for error in evaluation.errors)
        )
        self.assertEqual(
            self.recovery_service.get_recovery(
                "incident_1", recovery.recovery_id
            ).recovery_status.value,
            "proposed",
        )

    def test_unhealthy_environment_blocks_evaluation(self) -> None:
        recovery = self._completed_recovery()

        evaluation = self.service.create_evaluation(
            "incident_1",
            self._request(recovery, environment_healthy=False),
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.blocked)
        self.assertFalse(evaluation.recovery_verified)
        self.assertTrue(
            any("not confirmed healthy" in error for error in evaluation.errors)
        )

    def test_environment_mismatch_blocks_evaluation(self) -> None:
        recovery = self._completed_recovery()

        evaluation = self.service.create_evaluation(
            "incident_1",
            self._request(
                recovery, evaluation_environment_version="warehouse_v2"
            ),
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.blocked)
        self.assertTrue(
            any("differs from the recovery target" in error for error in evaluation.errors)
        )

    def test_tampered_recovered_artifact_blocks_evaluation(self) -> None:
        recovery = self._completed_recovery()
        self.assertIsNotNone(recovery.recovery_artifact_id)
        artifact_id = recovery.recovery_artifact_id
        assert artifact_id is not None
        recovered = self.provenance.get_artifact(artifact_id)
        recovered_path = self.config.artifact_root / recovered.artifact_path
        recovered_path.write_bytes(b"tampered")

        evaluation = self.service.create_evaluation(
            "incident_1", self._request(recovery)
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.blocked)
        self.assertFalse(evaluation.recovery_verified)
        self.assertTrue(
            any("integrity" in error for error in evaluation.errors)
        )

    def test_linked_recovery_artifact_must_match(self) -> None:
        recovery = self._completed_recovery()

        evaluation = self.service.create_evaluation(
            "incident_1",
            self._request(
                recovery,
                recovered_checkpoint_id="checkpoint_10",
            ),
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.blocked)
        self.assertTrue(
            any("not the artifact" in error for error in evaluation.errors)
        )

    def test_evaluation_without_recovery_is_not_recovery_verification(self) -> None:
        evaluation = self.service.create_evaluation(
            "incident_1", self._request(None)
        )

        self.assertEqual(evaluation.evaluation_status, EvaluationStatus.passed)
        self.assertFalse(evaluation.recovery_verified)
        self.assertEqual(
            evaluation.recovery_verification_status, EvaluationStatus.not_run
        )

    def test_no_valid_episodes_is_inconclusive(self) -> None:
        recovery = self._completed_recovery()

        evaluation = self.service.create_evaluation(
            "incident_1",
            self._request(
                recovery,
                recovered_episodes=self._episodes(
                    successes=[False, False],
                    rewards=[0.0, 0.0],
                    errors=["infra failure", "infra failure"],
                ),
            ),
        )

        self.assertEqual(
            evaluation.evaluation_status, EvaluationStatus.inconclusive
        )
        self.assertFalse(evaluation.recovery_verified)
        self.assertEqual(evaluation.evaluation_metrics["recovered"]["valid_episode_count"], 0)

    def test_idempotent_evaluation_request_returns_existing(self) -> None:
        recovery = self._completed_recovery()
        request = self._request(recovery, idempotency_key="eval-once")

        first = self.service.create_evaluation("incident_1", request)
        second = self.service.create_evaluation("incident_1", request)

        self.assertEqual(first.evaluation_id, second.evaluation_id)

    def test_lookup_scope_is_enforced(self) -> None:
        recovery = self._completed_recovery()
        evaluation = self.service.create_evaluation(
            "incident_1", self._request(recovery)
        )

        with self.assertRaises(EvaluationNotFoundError):
            self.service.get_evaluation("incident_other", evaluation.evaluation_id)

    def test_checkpoint_must_belong_to_supplied_run(self) -> None:
        recovery = self._completed_recovery()

        with self.assertRaises(EvaluationValidationError):
            self.service.create_evaluation(
                "incident_1",
                self._request(
                    recovery,
                    baseline_run_id="run_1",
                    baseline_checkpoint_id="baseline_checkpoint_10",
                ),
            )

    def test_acceptance_checks_are_explicit_and_report_observed_values(self) -> None:
        criteria = AcceptanceCriteria(
            minimum_recovered_success_rate=0.8,
            maximum_collision_rate=0.1,
        )
        baseline = summarize_episodes(
            self._episodes(
                successes=[True, True], rewards=[100.0, 100.0]
            )
        )
        recovered = summarize_episodes(
            self._episodes(
                successes=[True, False],
                rewards=[90.0, 50.0],
                collisions=[False, True],
            )
        )

        result = evaluate_acceptance(
            criteria=criteria, baseline=baseline, faulty=None, recovered=recovered
        )

        self.assertEqual(result["status"], "failed")
        by_name = {
            check["criterion"]: check for check in result["checks"]
        }
        self.assertEqual(
            by_name["minimum_recovered_success_rate"]["observed"], 0.5
        )
        self.assertFalse(
            by_name["minimum_recovered_success_rate"]["passed"]
        )
        self.assertEqual(by_name["maximum_collision_rate"]["observed"], 0.5)


if __name__ == "__main__":
    unittest.main()
