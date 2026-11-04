"""Shared-file review for the Studio session / provenance bridge change (project association).

The only change is an optional ``project_id``. A run started inside a project and an otherwise identical legacy run
must be indistinguishable to every consumer (config fingerprint, canonical events, artifacts, stored config), apart
from the association itself. Real short training runs; no model involved.
"""

from __future__ import annotations

import contextlib
import inspect
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.events.service import EventPublisher
from backend.studio.manager import manager
from backend.studio.provenance_bridge import RunBridge
from backend.studio.session import TrainingSession
from backend.studio.tests.test_studio import BASE

TRAINING = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2}


def _run(client: TestClient, project: str | None) -> str:
    headers = {} if project is None else {"X-Project-ID": project}
    body = {"agent": "PPO", "environment": "cartpole", "training": TRAINING, "env_params": {}, "agent_params": {}}
    created = client.post(f"{BASE}/sessions", json=body, headers=headers)
    assert created.status_code == 201, created.text
    sid = created.json()["session_id"]
    assert created.json()["project_id"] == project
    assert client.post(f"{BASE}/sessions/{sid}/start", headers=headers).status_code == 200
    deadline = time.time() + 60
    snap: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"{BASE}/sessions/{sid}", headers=headers).json()
        if snap.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert snap.get("status") == "completed", snap
    return snap["run_id"]


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    root = tmp_path_factory.mktemp("compat")
    mp = pytest.MonkeyPatch()
    mp.setenv("STUDIO_DATA_DIR", str(root / "studio"))
    mp.setenv("RL_STUDIO_DATA_ROOT", str(root / "var"))
    with TestClient(create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "Compat"}).json()["project_id"]
        legacy = _run(client, None)
        scoped = _run(client, project)
        yield {"client": client, "project": project, "legacy": legacy, "scoped": scoped}
        for session in list(manager._sessions.values()):
            with contextlib.suppress(Exception):
                session.stop()
            thread = getattr(session, "_thread", None)
            if thread is not None:
                thread.join(timeout=15)
        manager._sessions.clear()
    mp.undo()


def _db(pair: dict[str, Any]) -> Any:
    return pair["client"].app.state.database


def test_the_bridge_and_session_signatures_stay_backward_compatible() -> None:
    for owner in (RunBridge.__init__, TrainingSession.__init__):
        param = inspect.signature(owner).parameters["project_id"]
        assert param.default is None  # optional: callers that never heard of projects are unaffected
    # existing positional/keyword construction without project_id still binds
    inspect.signature(RunBridge.__init__).bind(
        None, "run", environment_id="e", environment_version="v", agent_id="a", config={}
    )
    inspect.signature(TrainingSession.__init__).bind(None, "ses_00000000", {}, "name")


def test_only_the_association_differs_between_a_project_run_and_a_legacy_run(pair: dict[str, Any]) -> None:
    with _db(pair).read() as db:
        rows = {r["run_id"]: dict(r) for r in db.execute("SELECT * FROM runs")}
    legacy, scoped = rows[pair["legacy"]], rows[pair["scoped"]]
    assert legacy["project_id"] is None and scoped["project_id"] == pair["project"]
    # the config fingerprint (the compatibility key used by recovery/provenance) is not affected by the project
    assert legacy["agent_config_fingerprint"] == scoped["agent_config_fingerprint"]
    assert legacy["environment_id"] == scoped["environment_id"] and legacy["environment_version"] == scoped["environment_version"]
    assert legacy["status"] == scoped["status"]


def test_canonical_events_are_identical_in_shape(pair: dict[str, Any]) -> None:
    def types(run: str) -> list[str]:
        events = EventPublisher.list_run_events(run)
        return sorted({e.event_type for e in events})

    assert types(pair["legacy"]) == types(pair["scoped"]) and "episode_end" in types(pair["scoped"])
    with _db(pair).read() as db:
        cols = {r["name"] for r in db.execute("PRAGMA table_info(events)")} if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='events'").fetchone() else set()
    assert "project_id" not in cols  # the event contract was not extended


def test_artifacts_and_stored_config_are_unaffected(pair: dict[str, Any]) -> None:
    with _db(pair).read() as db:
        counts = {
            run: db.execute("SELECT COUNT(*) FROM artifacts WHERE run_id = ?", (run,)).fetchone()[0]
            for run in (pair["legacy"], pair["scoped"])
        }
    assert counts[pair["legacy"]] == counts[pair["scoped"]] > 0
    client: TestClient = pair["client"]
    legacy_cfg = client.get(f"{BASE}/runs/{pair['legacy']}").json()["config"]
    scoped_cfg = client.get(f"{BASE}/runs/{pair['scoped']}", headers={"X-Project-ID": pair["project"]}).json()["config"]
    assert legacy_cfg == scoped_cfg and "project_id" not in scoped_cfg


def test_session_summary_exposes_the_association_without_changing_other_fields(pair: dict[str, Any]) -> None:
    client: TestClient = pair["client"]
    legacy = client.get(f"{BASE}/sessions").json()["sessions"][0]
    scoped = client.get(f"{BASE}/sessions", headers={"X-Project-ID": pair["project"]}).json()["sessions"][0]
    assert legacy["project_id"] is None and scoped["project_id"] == pair["project"]
    assert set(legacy) == set(scoped)
