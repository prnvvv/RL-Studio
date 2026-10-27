from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.provenance.exceptions import (
    ArtifactIntegrityError,
    IncidentNotFoundError,
    UnsafeArtifactPathError,
)
from backend.provenance.models import (
    ArtifactRegistration,
    IncidentRegistration,
    RunRegistration,
)
from backend.provenance.service import ProvenanceService


class ProvenanceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = DatabaseConfig.for_tests(Path(self.tempdir.name))
        self.db = Database(self.config)
        self.db.initialize()
        self.service = ProvenanceService(self.db)
        self.service.register_run(
            RunRegistration(
                run_id="run_1",
                environment_id="warehouse",
                environment_version="warehouse_v1",
                agent_config_fingerprint="ppo-abc",
            )
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write(self, relative: str, content: bytes = b"artifact") -> None:
        path = self.config.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _artifact(self, **kwargs):
        return self.service.register_artifact(ArtifactRegistration(**kwargs))

    def test_provenance_trace_and_artifact_listing(self) -> None:
        self._write("run_1/trajectory.npz", b"trajectory")
        self._write("run_1/checkpoint_10.zip", b"checkpoint-10")
        self._artifact(
            artifact_id="artifact_trajectory",
            run_id="run_1",
            artifact_type="trajectory",
            artifact_path="run_1/trajectory.npz",
            trajectory_id="trajectory_1",
            timestep=50,
        )
        self._artifact(
            artifact_id="artifact_checkpoint",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/checkpoint_10.zip",
            checkpoint_id="checkpoint_10",
            parent_artifact_id="artifact_trajectory",
            timestep=50,
            included_state_components=["policy", "optimizer"],
        )

        trace = self.service.get_run_provenance("run_1")
        self.assertEqual(trace.provenance_status.value, "complete")
        self.assertEqual(trace.lineage_completeness.value, "complete")
        self.assertEqual(trace.artifact_count, 2)
        self.assertEqual(len(trace.links), 1)
        self.assertEqual(trace.links[0].from_artifact_id, "artifact_trajectory")
        self.assertEqual(trace.links[0].to_artifact_id, "artifact_checkpoint")

        listing = self.service.list_run_artifacts("run_1")
        self.assertEqual(listing.count, 2)
        self.assertEqual(
            {item.artifact_id for item in listing.artifacts},
            {"artifact_trajectory", "artifact_checkpoint"},
        )

        artifact = self.service.get_artifact("artifact_checkpoint")
        self.assertEqual(artifact.checkpoint_id, "checkpoint_10")

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(UnsafeArtifactPathError):
            self._artifact(
                run_id="run_1",
                artifact_type="checkpoint",
                artifact_path="../outside.zip",
            )

    def test_hash_mismatch_is_rejected(self) -> None:
        self._write("run_1/checkpoint.zip", b"real-content")
        with self.assertRaises(ArtifactIntegrityError):
            self._artifact(
                run_id="run_1",
                artifact_type="checkpoint",
                artifact_path="run_1/checkpoint.zip",
                artifact_hash="0" * 64,
            )

    def test_missing_file_is_recorded_as_missing_not_available(self) -> None:
        artifact = self._artifact(
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/not-written.zip",
            timestep=10,
        )
        self.assertEqual(artifact.artifact_status.value, "missing")
        self.assertEqual(artifact.integrity_status.value, "missing")
        trace = self.service.get_run_provenance("run_1")
        self.assertEqual(trace.provenance_status.value, "incomplete")

    def test_impact_boundary_classification(self) -> None:
        for relative in (
            "run_1/trajectory.npz",
            "run_1/update.json",
            "run_1/cp_10.zip",
            "run_1/cp_50.zip",
            "run_1/cp_100.zip",
        ):
            self._write(relative)
        self._artifact(
            artifact_id="artifact_trajectory",
            run_id="run_1",
            artifact_type="trajectory",
            artifact_path="run_1/trajectory.npz",
            trajectory_id="trajectory_1",
            timestep=50,
        )
        self._artifact(
            artifact_id="artifact_update",
            run_id="run_1",
            artifact_type="policy_update",
            artifact_path="run_1/update.json",
            policy_update_id="update_1",
            timestep=55,
        )
        self._artifact(
            artifact_id="artifact_cp_10",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/cp_10.zip",
            checkpoint_id="checkpoint_10",
            timestep=10,
        )
        self._artifact(
            artifact_id="artifact_cp_50",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/cp_50.zip",
            checkpoint_id="checkpoint_50",
            timestep=50,
        )
        self._artifact(
            artifact_id="artifact_cp_100",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/cp_100.zip",
            checkpoint_id="checkpoint_100",
            timestep=100,
        )
        self.service.register_incident(
            IncidentRegistration(
                incident_id="incident_1",
                run_id="run_1",
                verification_id="verification_1",
                requirement_id="requirement_1",
                environment_version="warehouse_v1",
                source_environment_version="warehouse_v1",
                corruption_start_timestep=40,
                corruption_end_timestep=60,
                evidence_ids=["evidence_1"],
            )
        )

        impact = self.service.get_incident_impact("incident_1")
        self.assertEqual(impact.impact_status.value, "confirmed_exposed")
        self.assertAlmostEqual(impact.impact_score, 0.6, places=4)
        self.assertEqual(
            set(impact.affected_artifact_ids),
            {"artifact_trajectory", "artifact_update", "artifact_cp_50"},
        )
        self.assertEqual(impact.affected_trajectory_ids, ["trajectory_1"])
        self.assertEqual(impact.affected_policy_update_ids, ["update_1"])
        self.assertEqual(impact.affected_checkpoint_ids, ["checkpoint_50"])

        classifications = {
            entry["artifact_id"]: entry["classification"]
            for entry in impact.details["classifications"]
        }
        self.assertEqual(classifications["artifact_cp_10"], "not_exposed_based_on_recorded_lineage")
        self.assertEqual(classifications["artifact_cp_100"], "not_exposed_based_on_recorded_lineage")

    def test_incomplete_lineage_withholds_score_and_reports_unknown(self) -> None:
        self._write("run_1/cp_unknown.zip")
        self._artifact(
            artifact_id="artifact_cp_unknown",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/cp_unknown.zip",
            checkpoint_id="checkpoint_unknown",
        )
        self.service.register_incident(
            IncidentRegistration(
                incident_id="incident_unknown",
                run_id="run_1",
                source_environment_version="warehouse_v1",
                corruption_start_timestep=40,
                corruption_end_timestep=60,
            )
        )
        impact = self.service.get_incident_impact("incident_unknown")
        self.assertEqual(impact.impact_status.value, "unknown_incomplete_lineage")
        self.assertIsNone(impact.impact_score)
        self.assertTrue(impact.warnings)

    def test_exposure_propagates_through_parent_lineage(self) -> None:
        self._write("run_1/parent.zip")
        self._write("run_1/child.zip")
        self._artifact(
            artifact_id="artifact_parent",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/parent.zip",
            checkpoint_id="checkpoint_parent",
            timestep=50,
        )
        self._artifact(
            artifact_id="artifact_child",
            run_id="run_1",
            artifact_type="checkpoint",
            artifact_path="run_1/child.zip",
            checkpoint_id="checkpoint_child",
            parent_artifact_id="artifact_parent",
            environment_version="warehouse_v2",
            timestep=90,
        )
        self.service.register_incident(
            IncidentRegistration(
                incident_id="incident_prop",
                run_id="run_1",
                source_environment_version="warehouse_v1",
                corruption_start_timestep=40,
                corruption_end_timestep=60,
            )
        )
        impact = self.service.get_incident_impact("incident_prop")
        self.assertIn("artifact_child", impact.affected_artifact_ids)
        classifications = {
            entry["artifact_id"]: entry["classification"]
            for entry in impact.details["classifications"]
        }
        self.assertEqual(classifications["artifact_child"], "potentially_affected")

    def test_missing_incident_raises_not_found(self) -> None:
        with self.assertRaises(IncidentNotFoundError):
            self.service.get_incident_impact("does-not-exist")


if __name__ == "__main__":
    unittest.main()
