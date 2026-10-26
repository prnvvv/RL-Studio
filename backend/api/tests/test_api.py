from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.database.config import DatabaseConfig
from backend.provenance.models import (
    ArtifactRegistration,
    IncidentRegistration,
    RunRegistration,
)


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = DatabaseConfig.for_tests(Path(self.tempdir.name))
        self.client = TestClient(create_app(self.config))
        self.client.__enter__()
        self.services = self.client.app.state.services
        self._seed()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.tempdir.cleanup()

    def _write(self, relative: str, content: bytes) -> None:
        path = self.config.artifact_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _run(self, run_id: str) -> None:
        self.services.provenance.register_run(
            RunRegistration(
                run_id=run_id,
                environment_id="warehouse",
                environment_version="warehouse_v1",
                agent_config_fingerprint="ppo-abc",
            )
        )

    def _artifact(
        self, artifact_id: str, run_id: str, checkpoint_id: str, timestep: int
    ) -> None:
        relative = f"{run_id}/{checkpoint_id}.zip"
        self._write(relative, checkpoint_id.encode())
        self.services.provenance.register_artifact(
            ArtifactRegistration(
                artifact_id=artifact_id,
                run_id=run_id,
                artifact_type="checkpoint",
                artifact_path=relative,
                checkpoint_id=checkpoint_id,
                timestep=timestep,
                included_state_components=[
                    "policy",
                    "optimizer",
                    "rng",
                    "counters",
                ],
                metadata={
                    "serialization_format": "zip",
                    "observation_space": [4],
                    "action_space": [4],
                },
            )
        )

    def _seed(self) -> None:
        self._run("run_1")
        self._run("run_baseline")
        self._artifact("artifact_cp_10", "run_1", "checkpoint_10", 10)
        self._artifact(
            "artifact_cp_50", "run_1", "checkpoint_50", 50
        )
        self._artifact(
            "artifact_baseline", "run_baseline", "baseline_checkpoint", 10
        )
        self.services.provenance.register_incident(
            IncidentRegistration(
                incident_id="incident_1",
                run_id="run_1",
                verification_id="verification_1",
                environment_id="warehouse",
                environment_version="warehouse_v1",
                source_environment_version="warehouse_v1",
                corruption_start_timestep=40,
                corruption_end_timestep=60,
                evidence_ids=["evidence_1"],
            )
        )

    def _episodes(self, seeds: list[int]) -> list[dict]:
        return [
            {
                "episode_id": f"episode_{seed}",
                "seed": seed,
                "reward": 90.0,
                "episode_length": 50,
                "success": True,
            }
            for seed in seeds
        ]

    def test_openapi_exposes_all_person4_endpoints(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        expected = {
            "/api/v1/runs/{run_id}/provenance": "get",
            "/api/v1/runs/{run_id}/artifacts": "get",
            "/api/v1/artifacts/{artifact_id}": "get",
            "/api/v1/incidents/{incident_id}/impact": "get",
            "/api/v1/incidents/{incident_id}/recovery-assessments": "post",
            "/api/v1/incidents/{incident_id}/recovery-assessments/{assessment_id}": "get",
            "/api/v1/incidents/{incident_id}/recoveries": "post",
            "/api/v1/incidents/{incident_id}/recoveries/{recovery_id}": "get",
            "/api/v1/incidents/{incident_id}/evaluations": "post",
            "/api/v1/incidents/{incident_id}/evaluations/{evaluation_id}": "get",
        }
        self.assertEqual(set(paths), set(expected))
        for path, method in expected.items():
            self.assertIn(method, paths[path])

    def test_missing_artifact_returns_stable_error_shape(self) -> None:
        response = self.client.get("/api/v1/artifacts/artifact_missing")

        self.assertEqual(response.status_code, 404)
        body = response.json()["error"]
        self.assertEqual(body["code"], "PROV-002")
        self.assertTrue(body["message"])
        self.assertEqual(body["details"]["artifact_id"], "artifact_missing")
        self.assertTrue(body["correlation_id"])
        self.assertEqual(
            response.headers["X-Correlation-ID"], body["correlation_id"]
        )

    def test_invalid_request_body_returns_stable_validation_shape(self) -> None:
        response = self.client.post(
            "/api/v1/incidents/incident_1/recovery-assessments",
            json={"recovery_strategy": "unsupported_strategy"},
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()["error"]
        self.assertEqual(body["code"], "API-422")
        self.assertTrue(body["details"]["errors"])

    def test_provenance_artifact_and_impact_endpoints(self) -> None:
        provenance = self.client.get("/api/v1/runs/run_1/provenance")
        self.assertEqual(provenance.status_code, 200)
        self.assertEqual(provenance.json()["artifact_count"], 2)

        listing = self.client.get("/api/v1/runs/run_1/artifacts")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 2)

        artifact = self.client.get("/api/v1/artifacts/artifact_cp_50")
        self.assertEqual(artifact.status_code, 200)
        self.assertEqual(artifact.json()["checkpoint_id"], "checkpoint_50")

        impact = self.client.get("/api/v1/incidents/incident_1/impact")
        self.assertEqual(impact.status_code, 200)
        self.assertEqual(impact.json()["impact_status"], "confirmed_exposed")
        self.assertEqual(
            impact.json()["affected_checkpoint_ids"], ["checkpoint_50"]
        )

    def test_recovery_assessment_and_plan_endpoints(self) -> None:
        assessment_response = self.client.post(
            "/api/v1/incidents/incident_1/recovery-assessments",
            json={
                "source_checkpoint_id": "checkpoint_10",
                "target_environment_version": "warehouse_v1",
                "target_agent_config_fingerprint": "ppo-abc",
            },
            headers={"X-Correlation-ID": "corr-assessment"},
        )
        self.assertEqual(assessment_response.status_code, 201)
        assessment = assessment_response.json()
        self.assertEqual(assessment["recovery_eligibility"], "eligible")

        get_assessment = self.client.get(
            "/api/v1/incidents/incident_1/recovery-assessments/"
            f"{assessment['recovery_assessment_id']}"
        )
        self.assertEqual(get_assessment.status_code, 200)

        recovery_response = self.client.post(
            "/api/v1/incidents/incident_1/recoveries",
            json={
                "assessment_id": assessment["recovery_assessment_id"],
                "execute": False,
            },
        )
        self.assertEqual(recovery_response.status_code, 201)
        recovery = recovery_response.json()
        self.assertEqual(recovery["recovery_status"], "proposed")

        get_recovery = self.client.get(
            "/api/v1/incidents/incident_1/recoveries/"
            f"{recovery['recovery_id']}"
        )
        self.assertEqual(get_recovery.status_code, 200)
        self.assertEqual(get_recovery.json()["recovery_status"], "proposed")

    def test_evaluation_endpoint_without_recovery_link(self) -> None:
        response = self.client.post(
            "/api/v1/incidents/incident_1/evaluations",
            json={
                "baseline_run_id": "run_baseline",
                "baseline_checkpoint_id": "baseline_checkpoint",
                "recovered_run_id": "run_1",
                "recovered_checkpoint_id": "checkpoint_10",
                "evaluation_environment_version": "warehouse_v1",
                "environment_healthy": True,
                "baseline_episodes": self._episodes([1, 2, 3, 4]),
                "recovered_episodes": self._episodes([1, 2, 3, 4]),
                "acceptance_criteria": {
                    "minimum_recovered_success_rate": 0.8,
                    "maximum_success_rate_regression_vs_healthy": 0.0,
                    "minimum_valid_episodes_per_group": 4,
                    "require_no_episode_errors": True,
                },
            },
        )

        self.assertEqual(response.status_code, 201)
        evaluation = response.json()
        self.assertEqual(evaluation["evaluation_status"], "passed")
        self.assertFalse(evaluation["recovery_verified"])
        self.assertEqual(
            evaluation["recovery_verification_status"], "not_run"
        )
        self.assertEqual(evaluation["episode_count"], 4)

        loaded = self.client.get(
            "/api/v1/incidents/incident_1/evaluations/"
            f"{evaluation['evaluation_id']}"
        )
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(
            loaded.json()["details"]["acceptance_results"]["status"], "passed"
        )

    def test_scoped_lookup_returns_not_found(self) -> None:
        response = self.client.get(
            "/api/v1/incidents/incident_other/evaluations/evaluation_missing"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "EVAL-002")


if __name__ == "__main__":
    unittest.main()
