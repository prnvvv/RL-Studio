"""Trajectory persistence: every step, episode, update, evaluation and checkpoint is queryable."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.studio.manager import manager
from backend.studio.store import RunRecorder, TrajectoryReader

from .test_studio import BASE, _create, _wait, client  # noqa: F401  (client is a fixture)

TRAINING = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2}


def _run_to_completion(client: TestClient, **overrides: Any) -> tuple[str, dict[str, Any]]:
    sid = _create(client, **overrides)
    client.post(f"{BASE}/sessions/{sid}/start")
    snap = _wait(client, sid, {"completed", "failed"})
    assert snap["status"] == "completed", snap["error"]
    return sid, snap


def _all_steps(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    while True:
        page = client.get(f"{BASE}/runs/{run_id}/steps", params={"offset": len(steps), "limit": 1000}).json()["steps"]
        if not page:
            return steps
        steps += page


def test_every_step_is_persisted_with_consistent_transitions(client: TestClient) -> None:
    sid, snap = _run_to_completion(client, training=TRAINING)
    runs = client.get(f"{BASE}/sessions/{sid}/runs").json()["runs"]
    assert [r["run_id"] for r in runs] == [snap["run_id"]]
    run = runs[0]
    assert run["status"] == "completed" and run["config"]["agent"] == "PPO" and run["obs_shape"] == [4]
    assert run["step_count"] == snap["progress"]["timestep"] >= 2000

    steps = _all_steps(client, run["run_id"])
    assert len(steps) == run["step_count"]
    assert [s["step_index"] for s in steps] == list(range(steps[0]["step_index"], steps[0]["step_index"] + len(steps)))
    assert all(len(s["observation"]) == 4 and len(s["next_observation"]) == 4 for s in steps)
    assert all(a <= b for a, b in zip((s["timestamp"] for s in steps), (s["timestamp"] for s in steps[1:]), strict=False))

    # Inside an episode, the next observation of one step is the observation of the next.
    for current, following in zip(steps, steps[1:], strict=False):
        if current["episode"] == following["episode"]:
            assert current["next_observation"] == pytest.approx(following["observation"], abs=1e-6)
            assert not current["terminated"] and not current["truncated"]


def test_episode_rows_match_their_steps(client: TestClient) -> None:
    _, snap = _run_to_completion(client, training=TRAINING)
    run_id = snap["run_id"]
    episodes = client.get(f"{BASE}/runs/{run_id}/episodes").json()
    assert episodes["total"] == len(episodes["episodes"]) == len(snap["episodes"]) > 0
    steps = _all_steps(client, run_id)
    first = episodes["episodes"][0]
    own = [s for s in steps if s["episode"] == first["episode"]]
    assert len(own) == first["length"]
    assert math.isclose(sum(s["reward"] for s in own), first["reward"], rel_tol=1e-9)
    assert own[-1]["terminated"] or own[-1]["truncated"]
    only = client.get(f"{BASE}/runs/{run_id}/steps", params={"episode": first["episode"], "limit": 5000}).json()["steps"]
    assert [s["step_index"] for s in only] == [s["step_index"] for s in own]


def test_updates_evaluations_and_checkpoints_are_persisted(client: TestClient) -> None:
    _, snap = _run_to_completion(client, training=TRAINING)
    run_id = snap["run_id"]
    updates = client.get(f"{BASE}/runs/{run_id}/updates").json()["updates"]
    assert updates and "value_loss" in updates[0]
    evaluations = client.get(f"{BASE}/runs/{run_id}/evaluations").json()["evaluations"]
    assert evaluations and evaluations[0]["episodes"] == 2
    checkpoints = client.get(f"{BASE}/runs/{run_id}/checkpoints").json()["checkpoints"]
    assert {c["checkpoint_id"] for c in checkpoints} == {c["checkpoint_id"] for c in snap["checkpoints"]}
    assert all("path" not in c for c in checkpoints)


def test_off_policy_runs_record_observations_too(client: TestClient) -> None:
    training = {**TRAINING, "total_timesteps": 1500, "checkpoint_every": 0, "eval_every": 0}
    _, snap = _run_to_completion(client, agent="DQN", agent_params={"learning_starts": 100, "buffer_size": 2000}, training=training)
    steps = client.get(f"{BASE}/runs/{snap['run_id']}/steps", params={"limit": 50}).json()["steps"]
    assert steps and all(s["observation"] is not None and isinstance(s["action"], int) for s in steps)


def test_history_survives_losing_in_memory_sessions(client: TestClient) -> None:
    sid, snap = _run_to_completion(client, training=TRAINING)
    manager._sessions.clear()
    assert client.get(f"{BASE}/sessions/{sid}").status_code == 404
    assert client.get(f"{BASE}/runs/{snap['run_id']}").json()["step_count"] >= 2000
    assert client.get(f"{BASE}/sessions/{sid}/runs").json()["runs"][0]["status"] == "completed"


def test_reset_starts_a_new_run_without_erasing_the_old_one(client: TestClient) -> None:
    sid, first = _run_to_completion(client, training=TRAINING)
    client.post(f"{BASE}/sessions/{sid}/reset")
    client.post(f"{BASE}/sessions/{sid}/start")
    _wait(client, sid, {"completed", "failed"})
    runs = client.get(f"{BASE}/sessions/{sid}/runs").json()["runs"]
    assert [r["run_id"] for r in runs] == [first["run_id"], f"{sid}_r2"]
    assert all(r["step_count"] >= 2000 for r in runs)


def test_export_streams_jsonl_with_run_header(client: TestClient) -> None:
    _, snap = _run_to_completion(client, training={**TRAINING, "total_timesteps": 1000, "checkpoint_every": 0, "eval_every": 0})
    response = client.get(f"{BASE}/runs/{snap['run_id']}/export")
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert lines[0]["type"] == "run" and lines[0]["run_id"] == snap["run_id"]
    assert len(lines) - 1 == lines[0]["step_count"]
    assert {"observation", "action", "reward", "next_observation", "terminated"} <= set(lines[1])


@pytest.mark.parametrize("path", ["/runs/ses_deadbeef_r1", "/runs/..%2Fx", "/runs/ses_deadbeef_r1/steps", "/sessions/nope/runs"])
def test_unknown_runs_are_404(client: TestClient, path: str) -> None:
    assert client.get(f"{BASE}{path}").status_code == 404


def test_paging_limits_are_bounded(client: TestClient) -> None:
    _, snap = _run_to_completion(client, training={**TRAINING, "total_timesteps": 1000, "checkpoint_every": 0, "eval_every": 0})
    assert client.get(f"{BASE}/runs/{snap['run_id']}/steps", params={"limit": 999_999}).status_code == 422
    assert client.get(f"{BASE}/runs/{snap['run_id']}/steps", params={"offset": -1}).status_code == 422


def test_recorder_reports_storage_failures_instead_of_hiding_them(tmp_path) -> None:
    recorder = RunRecorder(tmp_path, "ses_00000000_r1")  # a directory is not a usable database file
    recorder.add_step(step_index=1, episode_step=1, obs=[0.0], action=0, reward=1.0, terminated=False, truncated=False, next_obs=[0.0])
    recorder.flush()
    assert recorder.healthy is False and recorder.last_error


def test_store_round_trips_float32_observations(tmp_path) -> None:
    path = tmp_path / "t.sqlite3"
    recorder = RunRecorder(path, "ses_00000001_r1")
    recorder.start_run(session_id="ses_00000001", run_index=1, name="t", agent="PPO", environment="cartpole", mode="training", config={"a": 1}, obs_shape=[2], created_at="x", started_at="x")
    recorder.add_step(step_index=1, episode_step=1, obs=[0.5, -1.25], action=[0.1, 0.2], reward=2.0, terminated=True, truncated=False, next_obs=[1.0, 2.0])
    recorder.end_episode(end_step=1, reward=2.0, length=1, success=True, reason="goal", collisions=0, disturbances=0)
    recorder.finish_run(status="completed", finished_at="y", error=None)
    step = TrajectoryReader(path).steps("ses_00000001_r1", episode=None, offset=0, limit=10)[0]
    assert step["observation"] == [0.5, -1.25] and step["action"] == [0.1, 0.2] and step["terminated"] is True
    assert TrajectoryReader(path).get_run("ses_00000001_r1")["episode_count"] == 1
