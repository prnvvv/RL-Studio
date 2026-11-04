"""Server-side project isolation across Studio, provenance, incidents, verification, events and sessions.

Real: Studio training runs (one inside a project, one legacy/unassigned), the real incident handoff, persisted
evidence. Mocked: only the hosted-model transport. Isolation is asserted from the backend's answers alone; no
frontend filtering is involved.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.app import create_app
from backend.studio.manager import manager
from backend.studio.tests.test_studio import BASE
from backend.verification.tests.phase3_support import (
    TRAINING,
    ScriptedProvider,
    make_ai,
    reward_proposal,
    statements_json,
)

P = "/api/v1/projects"
V = "/api/v1/verification"
IMPOSSIBLE = "the final episode reward must be at least 100000"
NOT_FOUND = "The requested record was not found."


def h(project_id: str | None) -> dict[str, str]:
    return {} if project_id is None else {"X-Project-ID": project_id}


def denied(response: Any) -> bool:
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    detail = body.get("detail") if isinstance(body, dict) else None
    return response.status_code == 404 and isinstance(detail, dict) and detail.get("error", {}).get("message") == NOT_FOUND


class World:
    client: TestClient
    p1: str
    p2: str
    run1: str  # owned by p1
    legacy: str  # unassigned
    sid1: str
    sid_legacy: str
    incident: str
    verification: str
    requirement: str
    intent: str
    artifact: str


def _train(client: TestClient, project: str | None) -> tuple[str, str]:
    body: dict[str, Any] = {"agent": "PPO", "environment": "cartpole", "training": TRAINING}
    response = client.post(f"{BASE}/sessions", json={**body, **({"project_id": project} if project else {})}, headers=h(project))
    assert response.status_code == 201, response.text
    sid = response.json()["session_id"]
    assert client.post(f"{BASE}/sessions/{sid}/start", headers=h(project)).status_code == 200
    deadline = time.time() + 60
    snap: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"{BASE}/sessions/{sid}", headers=h(project)).json()
        if snap.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert snap.get("status") == "completed", snap
    return sid, snap["run_id"]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[World]:
    root = tmp_path_factory.mktemp("scope")
    mp = pytest.MonkeyPatch()
    mp.setenv("STUDIO_DATA_DIR", str(root / "studio"))
    mp.setenv("RL_STUDIO_DATA_ROOT", str(root / "var"))
    w = World()
    with TestClient(create_app()) as client:
        w.client = client
        w.p1 = client.post(P, json={"name": "One"}).json()["project_id"]
        w.p2 = client.post(P, json={"name": "Two"}).json()["project_id"]
        w.sid1, w.run1 = _train(client, w.p1)
        w.sid_legacy, w.legacy = _train(client, None)

        provider = ScriptedProvider(statements_json(IMPOSSIBLE), [reward_proposal(IMPOSSIBLE, value=100000)])
        client.app.state.ai_service = make_ai(provider)  # type: ignore[attr-defined]
        intent = client.post(f"{P}/{w.p1}/intents", json={"statement": IMPOSSIBLE}, headers=h(w.p1)).json()["intents"][0]
        w.intent = intent["intent_id"]
        w.requirement = intent["requirements"][0]["requirement_id"]
        assert client.post(f"{P}/{w.p1}/requirements/{w.requirement}/confirm", headers=h(w.p1)).status_code == 200
        done = client.post(f"{P}/{w.p1}/verifications", json={"run_id": w.run1}, headers=h(w.p1)).json()
        w.verification = done["verification"]["verification_id"]
        w.incident = done["verification"]["incident"]["incident_id"]
        assert w.incident
        arts = client.get(f"/api/v1/runs/{w.run1}/artifacts", headers=h(w.p1)).json()
        items = arts if isinstance(arts, list) else arts.get("artifacts", arts.get("items", []))
        w.artifact = items[0]["artifact_id"]
        yield w
        for session in list(manager._sessions.values()):
            with contextlib.suppress(Exception):
                session.stop()
            thread = getattr(session, "_thread", None)
            if thread is not None:
                thread.join(timeout=15)
        manager._sessions.clear()
    mp.undo()


def urls(w: World) -> dict[str, str]:
    """One representative URL for every kind of project-owned record."""
    return {
        "studio run": f"{BASE}/runs/{w.run1}",
        "studio episodes": f"{BASE}/runs/{w.run1}/episodes",
        "studio checkpoints": f"{BASE}/runs/{w.run1}/checkpoints",
        "studio export": f"{BASE}/runs/{w.run1}/export",
        "studio history record": f"{BASE}/history/{w.run1}",
        "studio session": f"{BASE}/sessions/{w.sid1}",
        "studio session runs": f"{BASE}/sessions/{w.sid1}/runs",
        "provenance": f"/api/v1/runs/{w.run1}/provenance",
        "run artifacts": f"/api/v1/runs/{w.run1}/artifacts",
        "artifact": f"/api/v1/artifacts/{w.artifact}",
        "incident impact": f"/api/v1/incidents/{w.incident}/impact",
        "run requirements": f"{V}/runs/{w.run1}/requirements",
        "run intents": f"{V}/runs/{w.run1}/intents",
        "run verifications": f"{V}/runs/{w.run1}/verifications",
        "verification": f"{V}/verifications/{w.verification}",
        "verification results": f"{V}/verifications/{w.verification}/results",
        "requirement": f"{V}/requirements/{w.requirement}",
        "intent": f"{V}/intents/{w.intent}",
        "run status": f"/api/v1/runs/{w.run1}/status",
    }


def test_owner_scope_can_read_everything_it_owns(world: World) -> None:
    for name, url in urls(world).items():
        assert not denied(world.client.get(url, headers=h(world.p1))), name


@pytest.mark.parametrize("who", ["other", "none", "unknown", "malformed"])
def test_nobody_else_can_read_project_records_even_with_the_exact_ids(world: World, who: str) -> None:
    headers = {
        "other": h(world.p2),
        "none": {},
        "unknown": h("prj_ffffffffffffffff"),
        "malformed": {"X-Project-ID": "../../etc/passwd"},
    }[who]
    for name, url in urls(world).items():
        assert denied(world.client.get(url, headers=headers)), f"{name} leaked to {who}"


def test_the_query_parameter_scope_works_like_the_header(world: World) -> None:
    url = f"{BASE}/runs/{world.run1}"
    assert not denied(world.client.get(url, params={"project_id": world.p1}))
    assert denied(world.client.get(url, params={"project_id": world.p2}))
    assert denied(world.client.get(url))


def test_legacy_records_are_only_visible_unscoped_and_are_never_reassigned(world: World) -> None:
    c = world.client
    for url in (f"{BASE}/runs/{world.legacy}", f"{BASE}/sessions/{world.sid_legacy}", f"{BASE}/history/{world.legacy}"):
        assert not denied(c.get(url)), url  # unchanged legacy behaviour
        assert denied(c.get(url, headers=h(world.p1))), url  # hidden inside a project
        assert denied(c.get(url, headers=h(world.p2))), url
    with world.client.app.state.database.read() as db:  # type: ignore[attr-defined]
        assert db.execute("SELECT project_id FROM runs WHERE run_id = ?", (world.legacy,)).fetchone()[0] is None


def test_lists_only_contain_the_callers_project(world: World) -> None:
    c = world.client
    hist = lambda p: {e["run_id"] for e in c.get(f"{BASE}/history", headers=h(p)).json()["experiments"]}
    assert hist(world.p1) == {world.run1}
    assert hist(world.p2) == set()
    assert hist(None) == {world.legacy}  # unscoped sees only unassigned records

    sess = lambda p: {s["session_id"] for s in c.get(f"{BASE}/sessions", headers=h(p)).json()["sessions"]}
    assert sess(world.p1) == {world.sid1}
    assert sess(world.p2) == set()
    assert sess(None) == {world.sid_legacy}

    assert [r["run_id"] for r in c.get(f"{P}/{world.p1}/runs").json()["runs"]] == [world.run1]
    assert c.get(f"{P}/{world.p2}/runs").json()["runs"] == []
    assert world.run1 not in {r["run_id"] for r in c.get(f"{P}/legacy-runs").json()["runs"]}
    assert world.legacy in {r["run_id"] for r in c.get(f"{P}/legacy-runs").json()["runs"]}


def test_switching_projects_loads_only_the_selected_projects_data(world: World) -> None:
    c = world.client
    for _ in range(2):  # repeated switches / refreshes never carry anything over
        assert {e["run_id"] for e in c.get(f"{BASE}/history", headers=h(world.p1)).json()["experiments"]} == {world.run1}
        assert c.get(f"{BASE}/history", headers=h(world.p2)).json()["experiments"] == []
        assert c.get(f"{P}/{world.p2}/requirements", headers=h(world.p2)).json()["requirements"] == []
        assert len(c.get(f"{P}/{world.p1}/requirements", headers=h(world.p1)).json()["requirements"]) == 1


def test_websocket_events_are_scoped(world: World) -> None:
    c = world.client
    for headers in (h(world.p2), {}):
        with pytest.raises(WebSocketDisconnect), c.websocket_connect(f"/api/v1/events/{world.run1}", headers=headers):
            pass


def test_the_studio_live_stream_is_scoped(world: World) -> None:
    c = world.client
    for headers in (h(world.p2), {}):
        with pytest.raises(WebSocketDisconnect), c.websocket_connect(f"{BASE}/sessions/{world.sid1}/stream", headers=headers):
            pass
    with c.websocket_connect(f"{BASE}/sessions/{world.sid1}/stream?project_id={world.p1}") as ws:
        assert ws.receive_json()["type"] == "snapshot"


def test_a_session_is_created_in_exactly_one_project(world: World) -> None:
    c = world.client
    body = {"agent": "PPO", "environment": "cartpole", "training": TRAINING}
    mismatch = c.post(f"{BASE}/sessions", json={**body, "project_id": world.p1}, headers=h(world.p2))
    assert mismatch.status_code == 409
    no_scope = c.post(f"{BASE}/sessions", json={**body, "project_id": world.p1})
    assert no_scope.status_code == 409
    assert denied(c.post(f"{BASE}/sessions", json=body, headers=h("prj_ffffffffffffffff")))
    ok = c.post(f"{BASE}/sessions", json=body, headers=h(world.p2))
    assert ok.status_code == 201 and ok.json()["project_id"] == world.p2  # the scope alone assigns the project
    assert {s["session_id"] for s in c.get(f"{BASE}/sessions", headers=h(world.p2)).json()["sessions"]} == {ok.json()["session_id"]}


def test_project_api_cannot_verify_or_adopt_across_projects(world: World) -> None:
    c = world.client
    assert c.post(f"{P}/{world.p2}/verifications", json={"run_id": world.run1}).status_code == 404
    assert c.post(f"{P}/{world.p2}/runs/{world.run1}/adopt").status_code == 409  # owned, never reassigned


def test_a_deleted_project_is_hidden_but_its_data_is_retained(world: World) -> None:
    c = world.client
    doomed = c.post(P, json={"name": "Doomed"}).json()["project_id"]
    assert c.request("DELETE", f"{P}/{doomed}", json={"confirm_name": "Doomed"}).status_code == 200
    assert denied(c.get(f"{BASE}/history", headers=h(doomed)))  # its scope is no longer valid
    # the other projects and legacy data are unaffected
    assert {e["run_id"] for e in c.get(f"{BASE}/history", headers=h(world.p1)).json()["experiments"]} == {world.run1}


def test_shared_catalogue_endpoints_stay_available_unscoped(world: World) -> None:
    assert world.client.get(f"{BASE}/catalog").status_code == 200
    assert world.client.get("/health").status_code == 200
