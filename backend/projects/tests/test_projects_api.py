"""Project CRUD, documents and pre-training intent. No training run exists in any test here.

The hosted model is a scripted Groq transport (``ScriptedProvider``): these tests make no live provider call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from backend.projects.tests.doc_fixtures import DOCX_TYPE, make_docx, make_pdf
from backend.verification.tests.phase3_support import (
    SECRET,
    ScriptedProvider,
    make_ai,
    reward_proposal,
    statements_json,
)

P = "/api/v1/projects"
GOAL = "the final episode reward must be at least 1"


def _create(client: TestClient, name: str = "Alpha", **extra: Any) -> dict[str, Any]:
    response = client.post(P, json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _script(client: TestClient, *texts: str, proposals: list[dict[str, Any]] | None = None) -> ScriptedProvider:
    provider = ScriptedProvider(statements_json(*texts), proposals or [reward_proposal(t, value=1) for t in texts])
    client.app.state.ai_service = make_ai(provider)  # type: ignore[attr-defined]
    return provider


def test_create_list_rename_keeps_id_and_survives_restart(make_client: Callable[[], TestClient]) -> None:
    client = make_client()
    created = _create(client, "  My   project ", description="d", agent={"agent": "PPO"}, environment={"environment": "cartpole"})
    pid = created["project_id"]
    assert created["name"] == "My project" and created["training"]["state"] == "not_started"
    assert created["training"]["run_count"] == 0 and created["requirements"]["total"] == 0

    renamed = client.patch(f"{P}/{pid}", json={"name": "Renamed"}).json()
    assert renamed["project_id"] == pid and renamed["name"] == "Renamed" and renamed["created_at"] == created["created_at"]
    assert renamed["updated_at"] >= created["updated_at"]

    assert client.patch(f"{P}/{pid}", json={"name": ""}).status_code == 422
    assert client.post(P, json={"name": "x" * 500}).status_code == 422

    again = make_client()  # restart: a fresh app over the same databases
    listing = again.get(P).json()
    assert [p["project_id"] for p in listing["projects"]] == [pid]
    assert again.get(f"{P}/{pid}").json()["name"] == "Renamed"


def test_unknown_and_malformed_ids_are_not_found(client: TestClient) -> None:
    assert client.get(f"{P}/prj_0123456789abcdef").status_code == 404
    assert client.get(f"{P}/not-a-project").status_code == 422
    assert client.get(f"{P}/prj_0123456789abcdef/requirements").json()["detail"]["error"]["code"] == "not_found"


def test_delete_needs_exact_confirmation_and_is_a_soft_delete(client: TestClient) -> None:
    pid = _create(client, "Doomed")["project_id"]
    _script(client, GOAL)
    client.post(f"{P}/{pid}/intents", json={"statement": f"Please make sure {GOAL}."})

    wrong = client.request("DELETE", f"{P}/{pid}", json={"confirm_name": "doomed"})
    assert wrong.status_code == 409 and client.get(f"{P}/{pid}").status_code == 200

    done = client.request("DELETE", f"{P}/{pid}", json={"confirm_name": "Doomed"})
    assert done.status_code == 200 and done.json()["status"] == "deleted" and "kept" in done.json()["retained"]
    assert client.get(f"{P}/{pid}").status_code == 404
    assert client.get(P).json()["projects"] == []
    # nothing was destroyed: the Phase 3 records of the hidden project are still in the database
    db = client.app.state.database  # type: ignore[attr-defined]
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM verification_requirements WHERE run_id = ?", (f"project:{pid}",)).fetchone()[0] == 1
        assert conn.execute("SELECT status FROM projects WHERE project_id = ?", (pid,)).fetchone()[0] == "deleted"
    assert client.post(f"{P}/{pid}/intents", json={"statement": GOAL}).status_code == 404


def test_pre_training_intent_is_saved_validated_and_confirmable_without_any_run(make_client: Callable[[], TestClient]) -> None:
    client = make_client()
    pid = _create(client, "Pre", environment={"environment": "cartpole"})["project_id"]
    provider = _script(client, GOAL)
    statement = f"We want a reliable agent: {GOAL}."
    response = client.post(f"{P}/{pid}/intents", json={"statement": statement})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["stage"] == "pre_training" and body["run_id"] is None and body["requirement_count"] == 1
    intent = body["intents"][0]
    assert intent["run_id"] == f"project:{pid}" and intent["original_text"] == statement
    assert intent["source"]["type"] == "text" if "source" in intent else True
    req = intent["requirements"][0]
    # valid but not yet evaluable: kept as a draft awaiting run evidence, never rejected for lack of training
    assert req["lifecycle_status"] == "draft" and req["validation_status"] == "not_evaluable"
    assert req["awaiting_run_evidence"] is True and req["confirmation_status"] == "proposed"
    assert req["project_id"] == pid and req["requirement_revision"] == 1 and req["stage"] == "pre_training"
    assert [c["stage"] for c in provider.calls] == ["intent", "requirements"]
    assert SECRET not in response.text

    confirmed = client.post(f"{P}/{pid}/requirements/{req['requirement_id']}/confirm").json()
    assert confirmed["confirmation_status"] == "confirmed" and confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["expected_value"] == 1

    # no run, evidence or verification was invented
    assert client.get(f"{P}/{pid}/runs").json()["runs"] == []
    assert client.get(f"{P}/{pid}/verifications").json()["verifications"] == []
    detail = client.get(f"{P}/{pid}").json()
    assert detail["requirements"] == {"total": 1, "confirmed": 1, "pending": 0}
    assert detail["training"]["state"] == "not_started" and detail["last_verification"] is None

    restarted = make_client()  # persistence across a restart
    listed = restarted.get(f"{P}/{pid}/requirements").json()["requirements"]
    assert [(r["requirement_id"], r["confirmation_status"]) for r in listed] == [(req["requirement_id"], "confirmed")]
    # verifying without any run is refused rather than fabricated
    assert restarted.post(f"{P}/{pid}/verifications", json={"run_id": "ses_00000000_r1"}).status_code == 404


def test_ambiguous_requirement_asks_for_clarification_and_cannot_be_confirmed(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    vague = "the agent should be good"
    _script(client, vague, proposals=[reward_proposal(vague, op=None, value=None, needs_clarification=True,
                                                      clarification_question="What reward counts as good?")])
    req = client.post(f"{P}/{pid}/intents", json={"statement": f"Overall {vague}."}).json()["intents"][0]["requirements"][0]
    assert req["lifecycle_status"] == "needs_clarification" and req["clarification_question"]
    assert client.post(f"{P}/{pid}/requirements/{req['requirement_id']}/confirm").status_code == 409
    # the user supplies the missing numbers explicitly; the same lifecycle then accepts it
    ok = client.post(f"{P}/{pid}/requirements/{req['requirement_id']}/confirm",
                     json={"overrides": {"expected_value": 5, "comparison_operator": ">="}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["confirmation_status"] == "confirmed" and ok.json()["expected_value"] == 5


def test_reject_keeps_the_record(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    _script(client, GOAL)
    req = client.post(f"{P}/{pid}/intents", json={"statement": f"{GOAL}"}).json()["intents"][0]["requirements"][0]
    rejected = client.post(f"{P}/{pid}/requirements/{req['requirement_id']}/reject", json={"reason": "not wanted"}).json()
    assert rejected["lifecycle_status"] == "rejected" and rejected["confirmation_status"] == "rejected"
    assert len(client.get(f"{P}/{pid}/requirements").json()["requirements"]) == 1


def test_provider_failure_preserves_the_intent_and_never_invents_a_pass(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    provider = _script(client, GOAL)
    provider.mode = "down"
    statement = "Reward should be at least 5"
    response = client.post(f"{P}/{pid}/intents", json={"statement": statement})
    assert response.status_code == 201
    intent = response.json()["intents"][0]
    assert intent["original_text"] == statement
    assert intent["ai"]["origin"] in {"deterministic_parser", None} or intent["status"] == "provider_unavailable"
    assert "upstream detail" not in response.text and SECRET not in response.text
    stored = client.get(f"{P}/{pid}/intents").json()["intents"]
    assert [i["intent_id"] for i in stored] == [intent["intent_id"]]
    for r in client.get(f"{P}/{pid}/requirements").json()["requirements"]:
        assert r["confirmation_status"] != "confirmed"  # nothing became authoritative by itself


def test_empty_input_is_rejected(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    assert client.post(f"{P}/{pid}/intents", json={}).status_code == 422
    assert client.post(f"{P}/{pid}/intents", json={"statement": "   "}).status_code == 422


def test_create_with_initial_intent_survives_a_provider_failure(client: TestClient) -> None:
    provider = _script(client, GOAL)
    provider.mode = "down"
    response = client.post(P, json={"name": "Born with intent", "intent": {"statement": f"I need {GOAL}."}})
    assert response.status_code == 201
    assert response.json()["project_id"].startswith("prj_") and "intent" in response.json()


def test_documents_markdown_docx_pdf_feed_the_same_pipeline(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    md = f"# Goals\n\nThe agent must work. {GOAL}.\n".encode()
    up = client.post(f"{P}/{pid}/documents", params={"filename": "README.md"}, content=md, headers={"content-type": "text/markdown"})
    assert up.status_code == 201, up.text
    doc = up.json()["document"]
    assert doc["extraction_status"] == "extracted" and doc["sha256"] and doc["storage_reference"].endswith(".bin")
    assert doc["text_chars"] > 0 and ".md" not in doc["storage_reference"]

    dup = client.post(f"{P}/{pid}/documents", params={"filename": "copy.md"}, content=md, headers={"content-type": "text/markdown"})
    assert dup.status_code == 200 and dup.json()["duplicate"] and dup.json()["document"]["document_id"] == doc["document_id"]

    docx = client.post(f"{P}/{pid}/documents", params={"filename": "spec.docx"}, content=make_docx("Avoid collisions."),
                       headers={"content-type": DOCX_TYPE}).json()["document"]
    pdf = client.post(f"{P}/{pid}/documents", params={"filename": "spec.pdf"}, content=make_pdf("Reach the goal in 100 steps."),
                      headers={"content-type": "application/pdf"}).json()["document"]
    assert docx["extraction_status"] == pdf["extraction_status"] == "extracted"
    assert len(client.get(f"{P}/{pid}/documents").json()["documents"]) == 3

    provider = _script(client, GOAL)
    body = client.post(f"{P}/{pid}/intents", json={"document_ids": [doc["document_id"]]}).json()
    intent = body["intents"][0]
    assert GOAL in intent["original_text"] and intent["source"]["document_id"] == doc["document_id"]
    req = intent["requirements"][0]
    assert req["source"]["type"] == "document" and req["source"]["filename"] == "README.md"
    assert req["source_statement"] == GOAL and len(provider.calls) == 2


def test_invalid_documents_are_rejected_without_being_stored(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    cases = [
        ("fake.pdf", "application/pdf", b"not really a pdf"),
        ("run.exe", "application/octet-stream", b"MZ\x00\x00"),
        ("empty.txt", "text/plain", b""),
        ("a.txt", "application/pdf", b"hello"),
    ]
    for filename, ctype, data in cases:
        r = client.post(f"{P}/{pid}/documents", params={"filename": filename}, content=data, headers={"content-type": ctype})
        assert r.status_code == 422, (filename, r.text)
    assert client.get(f"{P}/{pid}/documents").json()["documents"] == []


def test_readable_type_without_text_is_stored_as_failed_and_cannot_be_used(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    r = client.post(f"{P}/{pid}/documents", params={"filename": "blank.md"}, content=b"   \n  ", headers={"content-type": "text/markdown"})
    doc = r.json()["document"]
    assert r.status_code == 201 and doc["extraction_status"] == "failed" and doc["extraction_error"]
    use = client.post(f"{P}/{pid}/intents", json={"document_ids": [doc["document_id"]]})
    assert use.status_code == 422


def test_documents_and_requirements_do_not_cross_projects(client: TestClient) -> None:
    a, b = _create(client, "A")["project_id"], _create(client, "B")["project_id"]
    doc = client.post(f"{P}/{a}/documents", params={"filename": "r.md"}, content=GOAL.encode(), headers={"content-type": "text/markdown"}).json()["document"]
    assert client.post(f"{P}/{b}/intents", json={"document_ids": [doc["document_id"]]}).status_code == 404
    _script(client, GOAL)
    req = client.post(f"{P}/{a}/intents", json={"statement": GOAL}).json()["intents"][0]["requirements"][0]
    assert client.post(f"{P}/{b}/requirements/{req['requirement_id']}/confirm").status_code == 404
    assert client.get(f"{P}/{b}/requirements").json()["requirements"] == []


def test_contradictory_sources_are_both_kept_and_flagged(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    high, low = "the final episode reward must be at least 100", "the final episode reward must be at most 10"
    _script(client, high, proposals=[reward_proposal(high, op=">=", value=100)])
    first = client.post(f"{P}/{pid}/intents", json={"statement": high}).json()["intents"][0]["requirements"][0]
    _script(client, low, proposals=[reward_proposal(low, op="<=", value=10)])
    second = client.post(f"{P}/{pid}/intents", json={"statement": low}).json()["intents"][0]["requirements"][0]
    listed = {r["requirement_id"]: r for r in client.get(f"{P}/{pid}/requirements").json()["requirements"]}
    assert len(listed) == 2
    assert listed[first["requirement_id"]]["conflicts_with"] == [second["requirement_id"]]
    assert client.post(f"{P}/{pid}/requirements/{first['requirement_id']}/confirm").status_code == 409
    client.post(f"{P}/{pid}/requirements/{second['requirement_id']}/reject")
    assert client.post(f"{P}/{pid}/requirements/{first['requirement_id']}/confirm").status_code == 200


def test_long_input_is_split_not_truncated_and_oversize_is_refused(client: TestClient) -> None:
    pid = _create(client)["project_id"]
    _script(client, GOAL)
    paragraphs = "\n\n".join(f"Paragraph {i}. " + ("filler words " * 120) for i in range(6))
    body = client.post(f"{P}/{pid}/intents", json={"statement": paragraphs + f"\n\n{GOAL}."}).json()
    assert len(body["intents"]) >= 2
    assert sum(len(i["original_text"]) for i in body["intents"]) >= len(paragraphs)
    huge = "\n\n".join("word " * 700 for _ in range(30))
    assert client.post(f"{P}/{pid}/intents", json={"statement": huge}).status_code == 422
