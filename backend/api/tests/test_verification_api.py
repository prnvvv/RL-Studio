"""HTTP API tests for the verification router.

The route only orchestrates: it adapts the payload, runs the real controller and
returns the serialised workflow output.  Tests inject the deterministic offline
investigator through ``app.state.verification_model_client`` so no request can
reach the network.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.database.config import DatabaseConfig
from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.exceptions import VerificationError
from backend.verification.llm.mock_client import OfflineMockMetaClient
from unit_testing.conftest import make_evidence, make_payload


class VerificationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = DatabaseConfig.for_tests(Path(self.tempdir.name))
        self.client = TestClient(create_app(self.config))
        self.client.__enter__()
        self.client.app.state.verification_model_client = OfflineMockMetaClient()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.tempdir.cleanup()

    def test_status_reports_deterministic_availability(self) -> None:
        response = self.client.get("/api/v1/verification/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertIs(body["deterministic_verification"], True)
        self.assertIn(body["meta_ai_provider"], {"configured", "unavailable"})

    def test_verify_runs_the_workflow_and_returns_json(self) -> None:
        response = self.client.post(
            "/api/v1/verification/verify",
            json=make_payload(evidence=make_evidence()),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["overall_status"], "fail")
        self.assertEqual(body["contract_status"], "violation")
        self.assertEqual(body["run_identifier"], "run_test_1")
        self.assertEqual(body["diagnosis"]["provider"], "offline_mock")
        self.assertIs(body["diagnosis"]["result"]["_metadata"]["live_request"], False)
        self.assertIn("anomalies", body)
        self.assertIn("consistency", body)

    def test_invalid_input_returns_422(self) -> None:
        response = self.client.post("/api/v1/verification/verify", json={})

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]["error"]
        self.assertEqual(detail["code"], "invalid_verification_input")

    def test_workflow_failure_returns_500_without_leaking_details(self) -> None:
        with mock.patch.object(
            VerificationAgentController,
            "run_verification_output",
            side_effect=VerificationError("internal detail that must not leak"),
        ):
            response = self.client.post(
                "/api/v1/verification/verify",
                json=make_payload(evidence=make_evidence()),
            )

        self.assertEqual(response.status_code, 500)
        detail = response.json()["detail"]["error"]
        self.assertEqual(detail["code"], "verification_failed")
        self.assertEqual(detail["details"]["reason"], "VERG-000")
        self.assertNotIn("internal detail", str(response.json()))
