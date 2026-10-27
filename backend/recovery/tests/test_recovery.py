from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.database.repositories import locks
from backend.provenance.models import (
    ArtifactRegistration,
    IncidentRegistration,
    RunRegistration,
)
from backend.provenance.service import ProvenanceService
from backend.recovery.exceptions import (
    AssessmentNotFoundError,
    RecoveryNotFoundError,
)
from backend.recovery.models import (
    Approval,
    RecoveryAssessmentRequest,
    RecoveryCreateRequest,
    RecoveryEligibility,
)
from backend.recovery.service import RecoveryService


class RecoveryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = DatabaseConfig.for_tests(Path(self.tempdir.name))
        self.db = Database(self.config)
        self.db.initialize()
        self.provenance = ProvenanceService(self.db)
        self.service = RecoveryService(self.db)
        self.provenance.register_run(
            RunRegistration(
                run_id="run_1",
                environment_id="warehouse",
                environment_version="warehouse_v1",
                agent_config_fingerprint="ppo-abc",
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

    def _write(self, relative: str, content: bytes = b"checkpoint") -> None:
        path = self.config.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _checkpoint(
        self,
        *,
        artifact_id: str = "artifact_cp_10",
        checkpoint_id: str = "checkpoint_10",
        timestep: int | None = 10,
        path: str = "run_1/cp_10.zip",
        metadata: dict | None = None,
        components: list[str] | None = None,
    ) -> None:
        self._write(path)
        self.provenance.register_artifact(
            ArtifactRegistration(
                artifact_id=artifact_id,
                run_id="run_1",
                artifact_type="checkpoint",
                artifact_path=path,
                checkpoint_id=checkpoint_id,
                timestep=timestep,
                included_state_components=(
                    ["policy", "optimizer", "rng", "counters"]
                    if components is None
                    else components
                ),
                metadata=metadata
                if metadata is not None
                else {
                    "serialization_format": "zip",
                    "observation_space": [4],
                    "action_space": [4],
                },
            )
        )

    def _assessment_request(self, **overrides) -> RecoveryAssessmentRequest:
        values = {
            "source_checkpoint_id": "checkpoint_10",
            "target_environment_version": "warehouse_v1",
            "target_agent_config_fingerprint": "ppo-abc",
        }
        values.update(overrides)
        return RecoveryAssessmentRequest(**values)

    def test_eligible_checkpoint_traceable_assessment(self) -> None:
        self._checkpoint()

        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        self.assertEqual(assessment.recovery_eligibility, RecoveryEligibility.eligible)
        self.assertEqual(assessment.source_checkpoint_id, "checkpoint_10")
        self.assertEqual(assessment.details["source_artifact_id"], "artifact_cp_10")
        self.assertIn("evidence_1", assessment.evidence_ids)
        outcomes = {check.name: check.outcome.value for check in assessment.compatibility}
        self.assertEqual(outcomes["checkpoint_file"], "pass")
        self.assertEqual(outcomes["content_hash"], "pass")
        self.assertEqual(outcomes["exposure_classification"], "pass")
        self.assertEqual(outcomes["algorithm_compatibility"], "pass")
        self.assertEqual(outcomes["environment_compatibility"], "pass")
        self.assertEqual(outcomes["serialization_compatibility"], "pass")
        self.assertEqual(outcomes["space_compatibility"], "pass")

        loaded = self.service.get_assessment(
            "incident_1", assessment.recovery_assessment_id
        )
        self.assertEqual(loaded.recovery_assessment_id, assessment.recovery_assessment_id)

    def test_checkpoint_inside_fault_interval_is_ineligible(self) -> None:
        self._checkpoint(timestep=50, path="run_1/cp_50.zip")

        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        self.assertEqual(
            assessment.recovery_eligibility, RecoveryEligibility.ineligible
        )
        outcomes = {check.name: check.outcome.value for check in assessment.compatibility}
        self.assertEqual(outcomes["exposure_classification"], "fail")

    def test_checkpoint_after_fault_interval_uses_recorded_lineage(self) -> None:
        self._checkpoint(timestep=100, path="run_1/cp_100.zip")

        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        self.assertEqual(assessment.recovery_eligibility, RecoveryEligibility.eligible)
        outcomes = {check.name: check.outcome.value for check in assessment.compatibility}
        self.assertEqual(outcomes["exposure_classification"], "pass")

    def test_missing_checkpoint_is_ineligible(self) -> None:
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request(source_checkpoint_id=None)
        )

        self.assertEqual(
            assessment.recovery_eligibility, RecoveryEligibility.ineligible
        )
        self.assertIn("source checkpoint not selected or not found", assessment.lineage_gaps)

    def test_missing_metadata_needs_review(self) -> None:
        self._checkpoint(metadata={}, components=[])

        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        self.assertEqual(
            assessment.recovery_eligibility, RecoveryEligibility.needs_review
        )
        self.assertTrue(assessment.lineage_gaps)
        self.assertIn("checkpoint state component metadata is missing", assessment.lineage_gaps)

    def test_target_environment_mismatch_needs_review(self) -> None:
        self._checkpoint()

        assessment = self.service.create_assessment(
            "incident_1",
            self._assessment_request(target_environment_version="warehouse_v2"),
        )

        self.assertEqual(
            assessment.recovery_eligibility, RecoveryEligibility.needs_review
        )
        outcomes = {check.name: check.outcome.value for check in assessment.compatibility}
        self.assertEqual(outcomes["environment_compatibility"], "unknown")

    def test_execution_requires_explicit_approval(self) -> None:
        self._checkpoint()
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        recovery = self.service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
                execute=True,
            ),
        )

        self.assertEqual(recovery.recovery_status.value, "blocked")
        self.assertIn("Human approval", recovery.failure_reason or "")
        self.assertFalse((self.config.artifact_root / "recovered").exists())

    def test_ineligible_recovery_is_blocked_even_with_approval(self) -> None:
        self._checkpoint(timestep=50, path="run_1/cp_50.zip")
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        recovery = self.service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
                execute=True,
                approval=Approval(approved=True, approved_by="operator_1"),
            ),
        )

        self.assertEqual(recovery.recovery_status.value, "blocked")
        self.assertIn("ineligible", recovery.failure_reason or "")
        self.assertFalse((self.config.artifact_root / "recovered").exists())

    def test_approved_execution_copies_checkpoint_atomically(self) -> None:
        self._checkpoint()
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )

        recovery = self.service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
                execute=True,
                approval=Approval(approved=True, approved_by="operator_1"),
                idempotency_key="recovery-request-1",
            ),
        )

        self.assertEqual(recovery.recovery_status.value, "completed")
        self.assertEqual(recovery.recovery_strategy.value, "restore_checkpoint")
        self.assertIsNotNone(recovery.recovery_artifact_id)
        self.assertIsNotNone(recovery.recovered_checkpoint_id)
        self.assertTrue(recovery.executed_actions)
        action_status = {action.action: action.status for action in recovery.executed_actions}
        self.assertEqual(action_status["restore_checkpoint"], "completed")
        self.assertEqual(action_status["discard_pending_rollouts"], "skipped")
        self.assertEqual(action_status["collect_fresh_experience"], "skipped")
        self.assertEqual(action_status["run_post_recovery_evaluation"], "proposed")
        self.assertTrue(recovery.warnings)
        self.assertTrue(
            any("requires a post-recovery evaluation" in warning for warning in recovery.warnings)
        )

        recovered_artifact = self.service.provenance.get_artifact(
            recovery.recovery_artifact_id or ""
        )
        self.assertEqual(recovered_artifact.artifact_type.value, "checkpoint")
        self.assertEqual(
            recovered_artifact.parent_artifact_id, "artifact_cp_10"
        )
        self.assertEqual(
            recovered_artifact.artifact_hash,
            self.service.provenance.get_artifact("artifact_cp_10").artifact_hash,
        )
        self.assertEqual(recovered_artifact.metadata["serialization_format"], "zip")
        self.assertEqual(
            recovered_artifact.metadata["recovered_from"], "artifact_cp_10"
        )
        recovered_path = self.config.artifact_root / recovered_artifact.artifact_path
        self.assertTrue(recovered_path.is_file())
        self.assertTrue((self.config.artifact_root / "run_1" / "cp_10.zip").is_file())

        loaded = self.service.get_recovery("incident_1", recovery.recovery_id)
        self.assertEqual(loaded.recovery_status.value, "completed")

    def test_idempotent_recovery_request_returns_existing(self) -> None:
        self._checkpoint()
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )
        request = RecoveryCreateRequest(
            assessment_id=assessment.recovery_assessment_id,
            idempotency_key="same-request",
        )

        first = self.service.create_recovery("incident_1", request)
        second = self.service.create_recovery("incident_1", request)

        self.assertEqual(first.recovery_id, second.recovery_id)

    def test_concurrent_recovery_lock_blocks_execution(self) -> None:
        self._checkpoint()
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )
        with self.db.write() as conn:
            locks.acquire_lock(
                conn,
                lock_key="recovery:run_1:artifact_cp_10",
                owner_id="other",
                ttl_seconds=300,
            )

        recovery = self.service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
                execute=True,
                approval=Approval(approved=True, approved_by="operator_1"),
            ),
        )

        self.assertEqual(recovery.recovery_status.value, "blocked")
        self.assertIn("already running", recovery.failure_reason or "")
        self.assertFalse((self.config.artifact_root / "recovered").exists())

    def test_lookup_scope_is_enforced(self) -> None:
        self._checkpoint()
        assessment = self.service.create_assessment(
            "incident_1", self._assessment_request()
        )
        recovery = self.service.create_recovery(
            "incident_1",
            RecoveryCreateRequest(
                assessment_id=assessment.recovery_assessment_id,
            ),
        )

        with self.assertRaises(AssessmentNotFoundError):
            self.service.get_assessment("incident_other", assessment.recovery_assessment_id)
        with self.assertRaises(RecoveryNotFoundError):
            self.service.get_recovery("incident_other", recovery.recovery_id)


if __name__ == "__main__":
    unittest.main()
