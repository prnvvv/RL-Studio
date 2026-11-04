"""Incident diagnosis, root-cause investigation and recovery recommendations.

Integration tests with MOCKED Meta responses: the database, provenance, verification store, evidence context builder,
LangGraph workflow, grounding rules, persistence, AIService and Meta client are all real; only the HTTP transport to
api.meta.ai is scripted. They prove the wiring and the safety rules. They do not prove that a live Meta call works
or that Muse Wonder is available to any account (see ``backend/ai/tests/test_live_meta_ai.py``).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from backend.ai.errors import AIAuthError, AIInvalidResponseError, AIQuotaError
from backend.diagnosis.context import IncidentContextBuilder
from backend.diagnosis.service import DiagnosisService, InvestigationNotFound
from backend.verification.storage.sqlite_store import SqliteVerificationStore

from .conftest import INCIDENT, RUN, VERIFICATION, Env

ROOT_CAUSE = {
    "summary": "Reward collapsed after the environment version changed.",
    "observed_facts": [
        {"statement": "Requirement req_1 failed deterministically (expected 200, actual 35).",
         "evidence_ids": [f"verification_result:{VERIFICATION}/req_1", "episode_7"]},
        {"statement": "A GPU memory leak was logged.", "evidence_ids": ["log:does-not-exist"]},
    ],
    "hypotheses": [
        {"component": "environment", "description": "The warehouse_v1 -> warehouse_v2 change corrupted rewards.",
         "supporting_evidence_ids": [f"incident:{INCIDENT}", "artifact:artifact_cp_50", "invented:ref"],
         "contradicting_evidence_ids": [], "confidence": 0.99, "uncertainty": "no direct trace of the reward function"},
        {"component": "agent", "description": "The learning rate may be too high.",
         "supporting_evidence_ids": ["nothing:real"], "confidence": 0.8, "uncertainty": "no config diff"},
    ],
    "missing_evidence": ["reward function source for warehouse_v2"],
    "recommended_investigation": ["diff the reward function between versions"],
    "limitations": ["only two checkpoints exist"],
    # the model tries to settle the case itself: must be ignored
    "root_cause_status": "confirmed", "overall_status": "PASS",
}

RECOVERY = {
    "summary": "Roll back to the last pre-corruption checkpoint.",
    "options": [
        {"action": "restore_checkpoint", "reason": "checkpoint_10 predates the corruption window",
         "supporting_evidence_ids": ["checkpoint:checkpoint_10", f"incident:{INCIDENT}"],
         "target_checkpoint_id": "checkpoint_10", "expected_impact": "removes affected experience",
         "risks": ["loses 40 steps of progress"], "preconditions": ["environment fixed to v1 behaviour"],
         "requires_user_authorization": False},
        {"action": "restore_checkpoint", "reason": "latest checkpoint", "supporting_evidence_ids": [],
         "target_checkpoint_id": "checkpoint_999", "requires_user_authorization": False},
        {"action": "rescore_experiences", "reason": "recompute rewards", "supporting_evidence_ids": ["episode_7"],
         "requires_user_authorization": False},
        {"action": "evaluate_only", "reason": "measure first", "supporting_evidence_ids": [f"incident:{INCIDENT}"],
         "requires_user_authorization": False},
    ],
    "not_recommended": ["restart_training: progress before corruption is recoverable"],
}


def svc(env: Env) -> DiagnosisService:
    return DiagnosisService(env.database, env.services.provenance, env.ai)


def builder(env: Env) -> IncidentContextBuilder:
    return IncidentContextBuilder(env.database, env.services.provenance, SqliteVerificationStore(env.database))


# --- context construction -------------------------------------------------------------------------


def test_context_is_built_only_from_persisted_records(make_env):
    env = make_env()
    ctx = builder(env).build(INCIDENT)
    index = ctx.evidence_index
    assert {f"incident:{INCIDENT}", f"run:{RUN}", "artifact:artifact_cp_10", "checkpoint:checkpoint_50", "evidence_1",
            f"verification:{VERIFICATION}", f"verification_result:{VERIFICATION}/req_1", "episode_7"} <= set(index)
    assert ctx.sufficient and ctx.run_id == RUN
    verification = ctx.payload["verification"]
    assert verification["non_passing_results"][0]["status"] == "fail" and verification["non_passing_results"][0]["actual"] == 35
    assert ctx.candidate_checkpoints["checkpoint_10"]["integrity_status"] in {"verified", "unverified"}
    assert builder(env).build(INCIDENT).context_hash == ctx.context_hash  # deterministic


def test_missing_evidence_is_reported_and_never_filled_in(make_env):
    env = make_env(verification=False, checkpoints=False, evidence=False)
    ctx = builder(env).build(INCIDENT)
    gaps = " | ".join(ctx.missing_evidence)
    assert "no evidence references" in gaps and "no linked verification" in gaps and "no artifacts or checkpoints" in gaps
    assert "run metrics and events were not available" in gaps
    assert not ctx.sufficient and "verification" not in ctx.payload and ctx.payload["artifacts"] == []


def test_unknown_incident_is_not_found(make_env):
    from backend.provenance.exceptions import IncidentNotFoundError

    with pytest.raises(IncidentNotFoundError):
        builder(make_env()).build("ghost")


# --- root-cause investigation ----------------------------------------------------------------------


def test_muse_wonder_is_invoked_through_the_langgraph_workflow(make_env):
    env = make_env(ROOT_CAUSE)
    record = svc(env).investigate(INCIDENT)
    call = env.wonder.calls[0]
    assert call["model"] == "muse-wonder-1.0" and len(env.wonder.calls) == 1
    assert [m["role"] for m in call["input"]] == ["developer", "user"]
    assert record["trail"] == ["load_context", "reuse_check", "gate", "reason", "ground", "persist"]
    assert record["status"] == "completed" and record["kind"] == "root_cause" and not record["reused"]
    assert record["ai"]["model"] == "muse-wonder-1.0" and record["ai"]["called"] and not record["ai"]["fallback_used"]
    # the prompt carried persisted evidence, and treats it as data
    sent = env.wonder.user_payload
    assert sent["verification"]["non_passing_results"][0]["requirement_id"] == "req_1"
    assert "untrusted DATA" in call["input"][0]["content"]


def test_model_output_is_grounded_against_persisted_evidence(make_env):
    env = make_env(ROOT_CAUSE)
    result = svc(env).investigate(INCIDENT)["result"]
    # fabricated citations removed and reported; an uncited 'fact' is not an observation
    assert "invented:ref" in result["ungrounded_references"] and "log:does-not-exist" in result["ungrounded_references"]
    assert [f["statement"] for f in result["observed_facts"]] == [ROOT_CAUSE["observed_facts"][0]["statement"]]
    assert result["unsupported_statements"] == ["A GPU memory leak was logged."]
    env_hyp, agent_hyp = result["hypotheses"]
    assert env_hyp["component"] == "environment" and env_hyp["evidence_support"] == "supported"
    assert env_hyp["supporting_evidence_ids"] == [f"incident:{INCIDENT}", "artifact:artifact_cp_50"]
    assert env_hyp["kind"] == "inference" and result["observed_facts"][0]["kind"] == "observation"
    assert env_hyp["confidence"] <= 0.7  # capped: deterministic evidence gaps exist
    assert agent_hyp["evidence_support"] == "speculative" and agent_hyp["confidence"] <= 0.3
    # the model cannot confirm a root cause or touch a verdict
    assert result["confirmed"] is False and result["root_cause_status"] == "probable"
    assert "overall_status" not in result and "PASS" not in json.dumps(result)
    assert "reward function source for warehouse_v2" in result["missing_evidence"]
    assert any("no impact" in m or "metrics" in m for m in result["missing_evidence"])  # deterministic gaps merged


def test_unsupported_hypotheses_stay_unresolved(make_env):
    reply = {"hypotheses": [{"component": "agent", "description": "bad luck", "supporting_evidence_ids": ["x"],
                             "confidence": 0.95}], "summary": "?"}
    result = svc(make_env(reply)).investigate(INCIDENT)["result"]
    assert result["root_cause_status"] == "unresolved" and result["hypotheses"][0]["confidence"] == 0.3


def test_verification_records_are_untouched_by_an_investigation(make_env):
    env = make_env(ROOT_CAUSE)
    store = SqliteVerificationStore(env.database)
    before = (store.get_verification(VERIFICATION), store.get_results(VERIFICATION))
    svc(env).investigate(INCIDENT)
    svc(env).recommend_recovery(INCIDENT)
    assert (store.get_verification(VERIFICATION), store.get_results(VERIFICATION)) == before


def test_insufficient_evidence_makes_no_model_call_and_is_persisted(make_env):
    env = make_env(ROOT_CAUSE, verification=False, checkpoints=False, evidence=False)
    record = svc(env).investigate(INCIDENT)
    assert not env.wonder.calls
    assert record["status"] == "insufficient_evidence" and record["ai"] == {"called": False}
    assert record["trail"] == ["load_context", "reuse_check", "gate", "persist"]
    assert record["result"]["missing_evidence"] and "no model was called" in record["result"]["message"]


def test_an_identical_context_reuses_the_stored_analysis_unless_forced(make_env):
    env = make_env(ROOT_CAUSE)
    first = svc(env).investigate(INCIDENT)
    second = svc(env).investigate(INCIDENT)
    assert len(env.wonder.calls) == 1 and second["reused"] and second["investigation_id"] == first["investigation_id"]
    third = svc(env).investigate(INCIDENT, force=True)
    assert len(env.wonder.calls) == 2 and third["investigation_id"] != first["investigation_id"]
    assert [r["investigation_id"] for r in svc(env).list(INCIDENT)] == [first["investigation_id"], third["investigation_id"]]


def test_changed_evidence_triggers_a_new_analysis(make_env):
    env = make_env(ROOT_CAUSE)
    svc(env).investigate(INCIDENT)
    # evidence changes when a new artifact is registered
    from backend.provenance.models import ArtifactRegistration

    path = env.config.artifact_root / f"{RUN}/cp_70.zip"
    path.write_bytes(b"x")
    env.services.provenance.register_artifact(ArtifactRegistration(
        artifact_id="artifact_cp_70", run_id=RUN, artifact_type="checkpoint", artifact_path=f"{RUN}/cp_70.zip",
        checkpoint_id="checkpoint_70", timestep=70, included_state_components=["policy"]))
    assert not svc(env).investigate(INCIDENT)["reused"] and len(env.wonder.calls) == 2


def test_stored_records_are_immutable_and_keep_the_evidence_index(make_env):
    env = make_env(ROOT_CAUSE)
    rec = svc(env).investigate(INCIDENT)
    stored = svc(env).get(INCIDENT, rec["investigation_id"])
    assert stored["result"] == rec["result"] and f"incident:{INCIDENT}" in stored["evidence_index"]
    with pytest.raises(InvestigationNotFound):
        svc(env).get("other_incident", rec["investigation_id"])
    with pytest.raises(InvestigationNotFound):
        svc(env).get(INCIDENT, "inv-missing")


# --- failures --------------------------------------------------------------------------------------


@pytest.mark.parametrize("reply", ["this is not json", {"hypotheses": "nope", "observed_facts": 7}, "[1, 2]"])
def test_malformed_model_output_is_rejected_and_nothing_is_persisted(make_env, reply):
    env = make_env(reply)
    with pytest.raises(AIInvalidResponseError):
        svc(env).investigate(INCIDENT)
    assert svc(env).list(INCIDENT) == []


def test_api_failures_are_typed_not_retried_when_permanent_and_never_fabricate(make_env):
    env = make_env(ROOT_CAUSE)
    env.wonder.fail = lambda r: httpx.Response(401, json={"error": {"type": "authentication_error"}})
    with pytest.raises(AIAuthError):
        svc(env).investigate(INCIDENT)
    assert len(env.wonder.calls) == 1
    env.wonder.calls.clear()
    env.wonder.fail = lambda r: httpx.Response(402, json={"error": {"type": "billing_error"}})
    with pytest.raises(AIQuotaError):
        svc(env).investigate(INCIDENT)
    assert svc(env).list(INCIDENT) == []


def test_transient_failures_retry_a_bounded_number_of_times(make_env):
    env = make_env(ROOT_CAUSE)
    env.wonder.fail = lambda r: httpx.Response(503)
    with pytest.raises(Exception) as info:
        svc(env).investigate(INCIDENT)
    # one initial attempt + META_API_MAX_RETRIES (1 in the test settings) for Wonder, then the Spark fallback's 2 attempts
    assert info.value.code == "AI-005" and 2 <= len(env.wonder.calls) <= 4


def test_wonder_unavailable_falls_back_to_spark_and_says_so(make_env):
    env = make_env(ROOT_CAUSE)
    original = env.wonder.__call__

    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["model"] == "muse-wonder-1.0":
            env.wonder.calls.append(json.loads(request.content))
            return httpx.Response(404, json={"error": {"type": "invalid_request_error", "code": "model_not_found"}})
        return original(request)

    env.ai.client._transport = httpx.MockTransport(handler)
    env.ai.client._sdk_client = None
    record = svc(env).investigate(INCIDENT)
    assert record["ai"]["fallback_used"] and record["ai"]["model"] == "muse-spark-1.3"
    assert any("preferred reasoning model was unavailable" in w for w in record["warnings"])


# --- recovery recommendations ------------------------------------------------------------------------


def test_recovery_recommendations_use_wonder_and_are_grounded(make_env):
    env = make_env(RECOVERY)
    env.wonder.reply = RECOVERY
    plan = svc(env).recommend_recovery(INCIDENT)
    assert env.wonder.calls[0]["model"] == "muse-wonder-1.0" and plan["kind"] == "recovery_plan"
    result = plan["result"]
    restore, bad_cp, rescore, _evaluate = result["options"]
    assert restore["target_checkpoint_id"] == "checkpoint_10" and restore["blocked_reason"] is None
    assert restore["mapped_strategy"] == "restore_checkpoint" and restore["executor_supported"]
    assert restore["next_step"].endswith("recovery_strategy=restore_checkpoint")
    assert bad_cp["target_checkpoint_id"] is None and "not a recorded checkpoint" in bad_cp["blocked_reason"]
    assert "checkpoint_999" in result["ungrounded_references"] and bad_cp["evidence_support"] == "speculative"
    assert rescore["executor_supported"] is False and rescore["mapped_strategy"] is None and rescore["next_step"] is None
    assert result["executed"] is False and all(o["executed"] is False for o in result["options"])


def test_authorization_is_always_required_for_state_changing_actions(make_env):
    env = make_env(RECOVERY)
    options = svc(env).recommend_recovery(INCIDENT)["result"]["options"]
    mutating = [o for o in options if o["action"] not in {"evaluate_only", "no_action"}]
    assert mutating and all(o["requires_user_authorization"] is True for o in mutating)  # the model said False
    assert next(o for o in options if o["action"] == "evaluate_only")["requires_user_authorization"] is False


def test_a_checkpoint_in_the_affected_set_is_blocked(make_env):
    env = make_env(RECOVERY)
    ctx = builder(env).build(INCIDENT)
    # the deterministic impact analysis marks which checkpoints the incident affects; mark one and re-ground
    ctx.candidate_checkpoints["checkpoint_10"]["affected_by_incident"] = True
    from backend.diagnosis.grounding import ground_recovery
    from backend.diagnosis.models import RecoveryPlan

    out = ground_recovery(RecoveryPlan.model_validate(RECOVERY), ctx)
    assert "affected set" in out["options"][0]["blocked_reason"] and out["options"][0]["next_step"] is None
    ctx.candidate_checkpoints["checkpoint_10"].update(affected_by_incident=False, integrity_status="mismatch")
    assert "integrity is mismatch" in ground_recovery(RecoveryPlan.model_validate(RECOVERY), ctx)["options"][0]["blocked_reason"]


def test_recovery_planning_builds_on_the_latest_root_cause_analysis(make_env):
    env = make_env(ROOT_CAUSE)
    analysis = svc(env).investigate(INCIDENT)
    env.wonder.reply = RECOVERY
    plan = svc(env).recommend_recovery(INCIDENT)
    sent = env.wonder.user_payload["prior_root_cause_analysis"]
    assert sent["investigation_id"] == analysis["investigation_id"] and "model inference" in sent["note"]
    assert plan["based_on_investigation_id"] == analysis["investigation_id"]


def test_recommendations_never_create_or_change_a_recovery(make_env):
    env = make_env(RECOVERY)
    svc(env).recommend_recovery(INCIDENT)
    from backend.database.repositories import recoveries as recoveries_repo

    with env.database.read() as conn:
        assert recoveries_repo.list_recoveries_for_incident(conn, INCIDENT) == []


# --- HTTP routes -------------------------------------------------------------------------------------------


def test_routes_investigate_list_get_and_recommend(make_env):
    env = make_env(ROOT_CAUSE)
    c = env.client
    r = c.post(f"/api/v1/incidents/{INCIDENT}/investigations", json={})
    assert r.status_code == 201 and r.json()["result"]["root_cause_status"] == "probable"
    again = c.post(f"/api/v1/incidents/{INCIDENT}/investigations")
    assert again.status_code == 200 and again.json()["reused"] and len(env.wonder.calls) == 1
    iid = r.json()["investigation_id"]
    assert c.get(f"/api/v1/incidents/{INCIDENT}/investigations").json()["count"] == 1
    assert c.get(f"/api/v1/incidents/{INCIDENT}/investigations/{iid}").json()["investigation_id"] == iid
    assert c.get(f"/api/v1/incidents/{INCIDENT}/investigations/inv-nope").status_code == 404
    env.wonder.reply = RECOVERY
    plan = c.post(f"/api/v1/incidents/{INCIDENT}/recovery-recommendations")
    assert plan.status_code == 201 and plan.json()["result"]["executed"] is False


def test_routes_unknown_incident_and_provider_failure(make_env):
    env = make_env(ROOT_CAUSE)
    assert env.client.post("/api/v1/incidents/ghost/investigations").status_code == 404
    env.wonder.fail = lambda r: httpx.Response(402, json={"error": {"type": "billing_error"}})
    r = env.client.post(f"/api/v1/incidents/{INCIDENT}/investigations", json={"force": True})
    assert r.status_code == 402 and r.json()["error"]["code"] == "AI-011"
    assert "meta_test_secret" not in r.text


def test_routes_reject_unknown_fields_and_report_status_without_secrets(make_env):
    env = make_env(ROOT_CAUSE)
    assert env.client.post(f"/api/v1/incidents/{INCIDENT}/investigations", json={"nope": 1}).status_code == 422
    status: dict[str, Any] = env.client.get("/api/v1/diagnosis/status").json()
    assert set(status["tasks"]) == {"root_cause_investigation", "investigation_assistance", "recovery_planning"}
    assert all(t["model"] == "muse-wonder-1.0" and t["model_access"] == "not_verified" for t in status["tasks"].values())


def test_routes_enforce_project_isolation(make_env):
    env = make_env(ROOT_CAUSE)
    c = env.client
    a = c.post("/api/v1/projects", json={"name": "Alpha"}).json()["project_id"]
    b = c.post("/api/v1/projects", json={"name": "Beta"}).json()["project_id"]
    with env.database.write() as conn:
        conn.execute("UPDATE runs SET project_id = ? WHERE run_id = ?", (a, RUN))
    url = f"/api/v1/incidents/{INCIDENT}/investigations"
    # another project, and the unscoped (legacy) view, get the same 404 and no model call is made
    assert c.post(url, headers={"X-Project-ID": b}).status_code == 404
    assert c.get(url, headers={"X-Project-ID": b}).status_code == 404
    assert c.post(url).status_code == 404
    assert c.post(f"/api/v1/incidents/{INCIDENT}/recovery-recommendations", headers={"X-Project-ID": b}).status_code == 404
    assert not env.wonder.calls
    # positive control: the owning project is served, so the 404s above are isolation and not a broken route
    owner = c.post(url, headers={"X-Project-ID": a})
    assert owner.status_code == 201 and len(env.wonder.calls) == 1
    assert c.get(url, headers={"X-Project-ID": b}).status_code == 404  # still hidden after it exists
