"""Tests for the Person 3 -> Person 4 incident handoff.

The handoff is detection-only: Person 3 builds an evidence-backed draft and
Person 4 owns persistence.  These tests assert that a draft is only produced for
a real deterministic failure, that no incident is invented, and that the public
``ProvenanceService`` contract round-trips the record.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.provenance.exceptions import RunNotFoundError
from backend.provenance.models import RunRegistration
from backend.provenance.service import ProvenanceService
from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.incidents.sink import (
    DETECTION_STATUS_CONFIRMED,
    P4_INCIDENT_STATUS,
    IncidentContractError,
    InMemoryIncidentSink,
    ProvenanceIncidentSink,
    build_incident_draft,
    build_registration,
)
from backend.verification.input.input_adapter import adapt_input
from backend.verification.llm.mock_client import OfflineMockMetaClient
from unit_testing.conftest import DEVELOPER_INTENT, make_evidence


def _canonical_output() -> dict:
    controller = VerificationAgentController(model_client=OfflineMockMetaClient())
    return controller.run_verification_output(
        adapt_input(
            {
                "agent_metadata": {"agent_id": "agent_incident", "agent_type": "ppo"},
                "developer_intent": DEVELOPER_INTENT,
                "environment_config": {"learning_rate": 0.001},
                "training_config": {"learning_rate": 0.001, "seed": 42},
                "execution_evidence": make_evidence(),
            }
        )
    )


class IncidentDraftTests(unittest.TestCase):
    def test_failure_output_produces_an_evidence_backed_draft(self) -> None:
        output = _canonical_output()

        draft = build_incident_draft(output)

        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertEqual(draft.run_id, "run_test_1")
        self.assertEqual(draft.environment_version, "warehouse_v1")
        self.assertEqual(draft.status, P4_INCIDENT_STATUS)
        self.assertEqual(draft.detection_status, DETECTION_STATUS_CONFIRMED)
        self.assertEqual(draft.detection_method, "deterministic_contract_check")
        self.assertIn("evt_reward_goal_1", draft.evidence_ids)
        self.assertEqual(
            draft.details["failed_requirement_count"],
            len(draft.details["failed_requirement_ids"]),
        )
        self.assertEqual(draft.details["detection_status"], DETECTION_STATUS_CONFIRMED)
        self.assertIn("consistency_status", draft.details)

    def test_passing_output_produces_no_incident(self) -> None:
        output = _canonical_output()
        passing = dict(output)
        passing["overall_status"] = "pass"

        self.assertIsNone(build_incident_draft(passing))

    def test_failure_without_run_identifier_is_rejected(self) -> None:
        output = dict(_canonical_output())
        output.pop("run_identifier", None)

        with self.assertRaises(IncidentContractError):
            build_incident_draft(output)

    def test_explicit_run_identifier_overrides_the_output(self) -> None:
        draft = build_incident_draft(_canonical_output(), run_id="run_explicit")

        assert draft is not None
        self.assertEqual(draft.run_id, "run_explicit")

    def test_non_mapping_output_is_rejected(self) -> None:
        with self.assertRaises(IncidentContractError):
            build_incident_draft(["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_registration_uses_the_public_person_four_contract(self) -> None:
        draft = build_incident_draft(_canonical_output())
        assert draft is not None

        registration = build_registration(draft)

        self.assertEqual(registration.incident_id, draft.incident_id)
        self.assertEqual(registration.run_id, draft.run_id)
        self.assertEqual(registration.status, P4_INCIDENT_STATUS)
        self.assertEqual(registration.evidence_ids, draft.evidence_ids)
        self.assertEqual(registration.details["detection_status"], DETECTION_STATUS_CONFIRMED)


class InMemoryIncidentSinkTests(unittest.TestCase):
    def test_recording_is_idempotent_for_the_same_run(self) -> None:
        draft = build_incident_draft(_canonical_output())
        assert draft is not None
        sink = InMemoryIncidentSink()

        first = sink.record(draft)
        second = sink.record(draft)

        self.assertEqual(first, second)
        self.assertEqual(sink.snapshot(), {"incidents": 1})
        self.assertEqual(sink.get(draft.incident_id)["run_id"], "run_test_1")

    def test_reusing_an_incident_id_for_another_run_fails(self) -> None:
        draft = build_incident_draft(_canonical_output())
        assert draft is not None
        sink = InMemoryIncidentSink()
        sink.record(draft)

        from dataclasses import replace

        with self.assertRaises(IncidentContractError):
            sink.record(replace(draft, run_id="run_other"))


class ProvenanceIncidentSinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.config = DatabaseConfig.for_tests(Path(self.tempdir.name))
        self.database = Database(self.config)
        self.database.initialize()
        self.provenance = ProvenanceService(self.database)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_incident_is_persisted_through_person_four_and_read_back(self) -> None:
        self.provenance.register_run(RunRegistration(run_id="run_test_1"))
        draft = build_incident_draft(_canonical_output())
        assert draft is not None

        stored = ProvenanceIncidentSink(self.provenance).record(draft)

        self.assertEqual(stored["incident_id"], draft.incident_id)
        self.assertEqual(stored["run_id"], "run_test_1")
        self.assertEqual(stored["status"], P4_INCIDENT_STATUS)
        self.assertEqual(stored["details"]["detection_status"], DETECTION_STATUS_CONFIRMED)

        read_back = self.provenance.get_incident(draft.incident_id)
        self.assertEqual(read_back.incident_id, draft.incident_id)
        self.assertEqual(read_back.evidence_ids, draft.evidence_ids)

    def test_unregistered_run_is_rejected_by_person_four(self) -> None:
        draft = build_incident_draft(_canonical_output())
        assert draft is not None

        with self.assertRaises(RunNotFoundError):
            ProvenanceIncidentSink(self.provenance).record(draft)
