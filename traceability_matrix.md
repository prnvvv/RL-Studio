# Traceability Matrix — Person 3 Verification Subsystem

Verified against code and executed tests on 2026-11-01, branch `backend3`.
Statuses: **PASS** implemented and verified, **PARTIAL** implemented but incomplete
or not fully tested, **FAIL** required functionality absent/broken, **BLOCKED**
requires approval or external integration, **NOT VERIFIED** insufficient evidence.

## Core contracts

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| A1 | Canonical models | `backend/verification/models.py` | PASS | Used by every test; Pydantic validation exercised in `unit_testing/test_offline_investigation.py::test_requirement_model_rejects_unsupported_type` |
| A2 | Protocol definitions | `backend/verification/interfaces.py` | PASS | Controller implements `VerificationService`; exercised by `test_prompts_and_support.py::test_controller_*` |
| A3 | Exception hierarchy | `backend/verification/exceptions.py` | PASS | `InputValidationError` and `PersistenceError` asserted in `test_prompts_and_support.py` |
| A4 | CheckStatus → contract status | `backend/verification/status_mapping.py` | PASS | `test_prompts_and_support.py::test_serialisation_adds_contract_status_without_removing_fields`; E2E asserts `contract_status="violation"` |

## Input layer

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| B1 | Input adapter | `backend/verification/input/input_adapter.py` | PASS | `adapt_input` drives `test_canonical_e2e.py` |
| B2 | Schema normaliser | `backend/verification/input/schema_normalizer.py` | PASS | Executed inside every workflow test; preserves extra keys |
| B3 | Context builder | `backend/verification/input/context_builder.py` | PASS | E2E asserts `run_identifier="run_test_1"`, `environment_version="warehouse_v1"` survive to output |

## Intent layer

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| C1 | Deterministic intent parser | `intent/intent_parser.py` | PASS | 8 intent cases in `test_prompts_and_support.py` (reward, steps, termination, forbidden event, ambiguity, empty intent) |
| C2 | Requirement extractor | `intent/requirement_extractor.py` | PASS | Metadata assertions: `test_named_forbidden_event_is_captured`, `test_step_bound_is_exposed_as_metadata` |
| C3 | Requirement registry / dispatch | `intent/requirement_registry.py`, `agent/workflow_planner.py` | PASS | Every pipeline test dispatches by requirement id; unknown types stay `unknown` |
| C4 | Requirement validator | `intent/intent_validator.py` | PASS | `unit_testing/test_intent_validator.py` (10 tests): valid reward/termination/config, missing expected value, vague reward left to parser, unsupported type, malformed model input, summary counts, empty list |

## Agent and workflow

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| D1 | Verification state | `agent/agent_state.py` | PASS | Full pipeline tests rely on state round-trip through LangGraph |
| D2 | Controller over the graph | `agent/agent_controller.py` | PASS | `test_prompts_and_support.py::test_controller_runs_the_workflow_and_persists_results`; canonical E2E |
| D3 | Workflow planner | `agent/workflow_planner.py` | PASS | Registry-driven dispatch exercised by all pipeline tests |
| D4 | LangGraph workflow + conditional routing | `agent/verification_agent.py` | PASS | `test_workflow_routing.py` (6 tests): normalize/plan short-circuits, PASS skips investigation, failure routes to investigate, `investigate=False`, missing provider |
| D5 | Decision engine | `agent/decision_engine.py` | PASS | `test_mandatory_failure_can_never_be_reported_as_pass`; PASS/UNKNOWN aggregation cases |
| D6 | Result aggregator facade | `result_aggregator.py` | PASS | Exercised through workflow aggregation |
| D7 | Result serializer | `result_serializer.py` | PASS | `test_serialisation_adds_contract_status_without_removing_fields`; `test_controller_output_payload_is_json_safe` |
| D8 | Result validator | `result_validator.py` | PASS | `test_confirmed_root_cause_without_evidence_is_downgraded`; `test_missing_investigation_fields_are_reported_not_invented` |

## Deterministic checks

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| F1 | Evidence bundle / validation / redaction | `evidence_validator.py` | PASS | Bounded+redacted bundle used by investigation; `test_analysis_reports_missing_evidence_instead_of_guessing` |
| F2 | Reward checker | `tools/reward_checker.py` | PASS | `test_tools.py` 5 cases; E2E expected 25.0 vs actual 5.0 |
| F3 | Episode checker | `tools/episode_checker.py` | PASS | Termination/truncation/goal/step-bound tests in `test_tools.py` and `test_agent_pipeline.py` |
| F4 | Event checker | `tools/event_checker.py` | PASS | Required/forbidden/order/count/dedup/evidence-completeness tests |
| F5 | Metric checker | `tools/metric_checker.py` | PASS | `test_all_observations_evaluated`, NaN, infinity tests |
| F6 | Configuration checker | `tools/configuration_checker.py` | PASS | `test_learning_rate_mismatch_is_a_violation`; non-numeric and infinity cases |
| F7 | Missing evidence never PASS | all checkers + decision engine | PASS | `test_absent_evidence_keeps_every_requirement_unevaluated`, `test_missing_observed_reward_is_unknown_not_zero` |
| F8 | Contradictory-evidence detection | `consistency_checker.py` | PASS | `detect_evidence_contradictions` covers episode goal-without-termination, conflicting duplicate events, conflicting duplicate metrics (identity-keyed) and environment/training config conflicts; verified in `test_analysis_integration.py` and surfaced as `consistency.contradictions` |

## Meta AI boundary

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| E1 | Real provider transport | `llm/meta_ai.py` | PASS | `test_meta_ai_offline.py`: URL resolution/bearer header, bounded retry, no-retry on auth, typed invalid-JSON error, missing/empty credentials, tool-use disabled (9 tests, `httpx.MockTransport`, no live calls) |
| E2 | Prompt templates | `llm/prompts.py` | PASS | `test_partial_prompt_substitution_never_raises`, `test_unknown_prompt_name_is_rejected` |
| E3 | Response parsing / validation | `llm/response_parser.py` | PASS | Invalid JSON classified as typed error; investigation result validated in the workflow |
| E4 | Guardrails (injection/tool policy) | `llm/llm_guardrails.py`, `agent/verification_agent.py` | PASS | `apply_guardrails` runs in `node_investigate` for every provider; `unit_testing/test_guardrails_investigation.py` (5 tests): valid offline output, schema rejection, missing fields reported, unbacked confirmed cause downgraded, prompt injection rejected — verdict unchanged in each case |
| E5 | Offline investigator | `llm/mock_client.py` | PASS | `test_offline_mock_completes_without_any_live_request`, canonical E2E; metadata `offline=true`, `live_request=false`; confidence `None`; root cause `unresolved` |

## Analysis helpers

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| H1 | Anomaly detector | `anomaly_detector.py`, `agent/verification_agent.py` | PASS | Executed in the advisory `analyze` stage; `test_analysis_integration.py` asserts no anomaly for a stable series, one z-score anomaly with its metric ref, and that an anomaly cannot turn a PASS into a failure |
| H2 | Consistency checker | `consistency_checker.py`, `agent/verification_agent.py` | PASS | Serialised `consistency` block with `status`/`consistent`/`problems`/`contradictions`/`evidence_available`; missing evidence reports `not_evaluable`, not `consistent` (`test_analysis_integration.py`) |

## Reporting, persistence, API

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| G1 | Report builder | `report_builder.py` | PASS | `test_report_records_unavailable_investigation_as_a_limitation`; canonical E2E report test |
| G2 | In-memory storage | `storage/verification_store.py` | PASS | `test_storage_is_append_only_and_returns_copies`, `test_storage_rejects_unknown_identifiers`, E2E snapshot counts |
| G3 | Diagnosis and serialisation | `agent/verification_agent.py`, `result_serializer.py` | PASS | Canonical E2E asserts diagnosis status/provider, JSON-safe output, provenance fields |
| I1 | Verification HTTP API invoking the graph | `backend/api/routers/verification.py`, `backend/api/app.py` | PASS | `GET /api/v1/verification/status` and `POST /api/v1/verification/verify` invoke the real `VerificationAgentController`; `backend/api/tests/test_verification_api.py` (4 tests): status, success with offline client, invalid input 422, workflow failure 500 with no internal detail leak |
| J1 | Durable persistence | `backend/database/` (P4) | PARTIAL | Verification records remain in the in-memory store; durable verification persistence is Person 4's boundary and was not added |
| J2 | Incident linkage | `backend/verification/incidents/sink.py`, `backend/provenance/service.py` (P4) | PARTIAL | P3-owned sink builds an evidence-backed draft only for a real failure and registers it through P4's public `ProvenanceService`; `unit_testing/test_incident_sink.py` verifies persistence and read-back against SQLite. P4 adoption confirmation outstanding; no P4 module modified |
| J3 | Shared requirement schema compatibility | `shared/`, `backend/verification/intent/shared_adapter.py` | PARTIAL | Bidirectional adapter with lossless round-trip verified in `unit_testing/test_shared_schema_adapter.py` (7 tests); shared schema unchanged, so no owner approval was required or requested |
| K1 | Canonical end-to-end (offline model) | `unit_testing/test_canonical_e2e.py` | PASS | Controller → graph → checks → serialisation → storage, canonical reward-scaling evidence, offline investigator |

## Totals

- PASS: 39
- PARTIAL: 3 (J1, J2, J3)
- FAIL: 0
- BLOCKED: 0
- Total: 42

Fully verified: **39/42 (93%)**. Implemented (PASS+PARTIAL): **42/42 (100%)**.

## Test evidence (2026-11-01)

```
python -m pytest backend/verification/tests -q   -> 20 passed
python -m pytest unit_testing -q                 -> 103 passed
python -m pytest backend/api/tests -q            -> 11 passed
python -m pytest backend/verification/tests unit_testing backend/api/tests -q -> 134 passed
python -m pytest unit_testing/test_canonical_e2e.py -q -> 2 passed
python -m pytest unit_testing/test_workflow_routing.py -q -> 6 passed
python -m ruff check backend/verification unit_testing backend/api -> All checks passed
```

No live Meta Model API request was made in any test.
