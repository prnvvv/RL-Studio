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
| C4 | Requirement validator | `intent/intent_validator.py` | PARTIAL | Exported and implemented; no dedicated positive/negative tests |

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
| F8 | Contradictory-evidence detection | n/a | PARTIAL | Aggregation blocks non-PASS upgrades, but no dedicated contradiction detector; investigator `contradicting_evidence` is always empty |

## Meta AI boundary

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| E1 | Real provider transport | `llm/meta_ai.py` | PASS | `test_meta_ai_offline.py`: URL resolution/bearer header, bounded retry, no-retry on auth, typed invalid-JSON error, missing/empty credentials, tool-use disabled (9 tests, `httpx.MockTransport`, no live calls) |
| E2 | Prompt templates | `llm/prompts.py` | PASS | `test_partial_prompt_substitution_never_raises`, `test_unknown_prompt_name_is_rejected` |
| E3 | Response parsing / validation | `llm/response_parser.py` | PASS | Invalid JSON classified as typed error; investigation result validated in the workflow |
| E4 | Guardrails (injection/tool policy) | `llm/llm_guardrails.py` | PARTIAL | Implemented and exported; not applied by `node_investigate` and has no tests |
| E5 | Offline investigator | `llm/mock_client.py` | PASS | `test_offline_mock_completes_without_any_live_request`, canonical E2E; metadata `offline=true`, `live_request=false`; confidence `None`; root cause `unresolved` |

## Analysis helpers

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| H1 | Anomaly detector | `anomaly_detector.py` | PARTIAL | Implemented; not invoked by the workflow; no tests |
| H2 | Consistency checker | `consistency_checker.py`, `validation/__init__.py` | PARTIAL | Implemented and re-exported; not invoked by the workflow; no tests |

## Reporting, persistence, API

| ID | Requirement | Files | Status | Evidence |
|---|---|---|---|---|
| G1 | Report builder | `report_builder.py` | PASS | `test_report_records_unavailable_investigation_as_a_limitation`; canonical E2E report test |
| G2 | In-memory storage | `storage/verification_store.py` | PASS | `test_storage_is_append_only_and_returns_copies`, `test_storage_rejects_unknown_identifiers`, E2E snapshot counts |
| G3 | Diagnosis and serialisation | `agent/verification_agent.py`, `result_serializer.py` | PASS | Canonical E2E asserts diagnosis status/provider, JSON-safe output, provenance fields |
| I1 | Verification HTTP API invoking the graph | `backend/api/` | FAIL | No verification router exists; `backend/api/app.py` registers only provenance/recovery/evaluation + operational routes. Fix modifies shared API composition → approval required |
| J1 | Durable persistence | `backend/database/` (P4) | PARTIAL | Only the in-memory store is implemented; database persistence is Person 4's boundary |
| J2 | Incident linkage | `backend/database/`, `backend/provenance/` (P4) | BLOCKED | No incident record is created; needs an agreed P3→P4 contract |
| J3 | Shared requirement schema compatibility | `shared/` | BLOCKED | Explicit owner approval required; unchanged in this audit |
| K1 | Canonical end-to-end (offline model) | `unit_testing/test_canonical_e2e.py` | PASS | Controller → graph → checks → serialisation → storage, canonical reward-scaling evidence, offline investigator |

## Totals

- PASS: 33
- PARTIAL: 6 (C4, F8, E4, H1, H2, J1)
- FAIL: 1 (I1)
- BLOCKED: 2 (J2, J3)
- Total: 42

Fully verified: **33/42 (79%)**. Implemented (PASS+PARTIAL): **39/42 (93%)**.

## Test evidence (2026-11-01)

```
python -m pytest backend/verification/tests -q   -> 20 passed
python -m pytest unit_testing -q                 -> 62 passed
python -m pytest backend/api/tests -q            -> 7 passed
python -m pytest unit_testing/test_canonical_e2e.py -q -> 2 passed
python -m pytest unit_testing/test_workflow_routing.py -q -> 6 passed
python -m ruff check backend/verification unit_testing -> All checks passed
```

No live Meta Model API request was made in any test.
