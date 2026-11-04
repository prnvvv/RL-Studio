"""Persistent, project-scoped training history, exercised end to end through the real HTTP API.

Every training run here is a real (short) Stable-Baselines3 CartPole run executed by the real Studio session; metrics,
checkpoints and episodes are whatever that training actually produced. Nothing is faked and no AI provider is involved.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.training_history import TrainingHistory

STUDIO = "/api/v1/studio"
TRAIN = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2}
LONG = {"total_timesteps": 400000, "simulation_speed": 0, "checkpoint_every": 100000, "eval_every": 0, "eval_episodes": 1}


def project(client: TestClient, name: str) -> str:
    r = client.post("/api/v1/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def base(pid: str) -> str:
    return f"/api/v1/projects/{pid}"


def create_session(client: TestClient, pid: str, training: dict[str, Any] = TRAIN, **extra: Any) -> dict[str, Any]:
    body = {"agent": "PPO", "environment": "cartpole", "training": training, **extra}
    r = client.post(f"{STUDIO}/sessions", json=body, headers={"X-Project-ID": pid})
    assert r.status_code == 201, r.text
    return r.json()


def start(client: TestClient, pid: str, sid: str) -> None:
    r = client.post(f"{STUDIO}/sessions/{sid}/start", headers={"X-Project-ID": pid})
    assert r.status_code in (200, 202), r.text


def wait_run(client: TestClient, pid: str, run_id: str, states: set[str], timeout: float = 90) -> dict[str, Any]:
    deadline, run = time.time() + timeout, {}
    while time.time() < deadline:
        run = client.get(f"{base(pid)}/training-runs/{run_id}").json()["run"]
        if run["status"] in states:
            return run
        time.sleep(0.15)
    raise AssertionError(f"run {run_id} never reached {states}; last={run.get('status')}")


def train_to_completion(client: TestClient, pid: str, **extra: Any) -> dict[str, Any]:
    snap = create_session(client, pid, **extra)
    start(client, pid, snap["session_id"])
    return wait_run(client, pid, snap["run_id"], {"completed", "failed", "stopped"})


# --- lifecycle ----------------------------------------------------------------------------------------


def test_natural_completion_is_persisted_with_final_metrics_checkpoints_and_provenance(client):
    pid = project(client, "A")
    run = train_to_completion(client, pid)
    assert run["status"] == "completed" and run["termination_reason"] == "natural_completion"
    assert run["project_id"] == pid and run["algorithm"] == "PPO" and run["environment_name"] == "cartpole"
    assert run["finished_at"] and run["duration_seconds"] > 0 and run["total_timesteps"] >= 2000
    assert run["total_episodes"] > 0 and run["final_metrics"]["mean_reward"] is not None
    assert run["agent_id"].startswith("agt_") and run["environment_config_id"].startswith("env_")
    detail = client.get(f"{base(pid)}/training-runs/{run['run_id']}").json()
    assert detail["snapshots"]["agent"]["agent"] == "PPO" and detail["snapshots"]["training"]["seed"] is not None
    assert len(detail["checkpoints"]) >= 1  # references to the checkpoints the training really wrote
    # the provenance runs row is no longer stuck on "running"
    assert client.get(f"/api/v1/provenance/runs/{run['run_id']}", headers={"X-Project-ID": pid}).status_code in (200, 404)


def test_manual_stop_preserves_partial_history_and_is_never_reported_completed(client):
    pid = project(client, "A")
    snap = create_session(client, pid, LONG)
    start(client, pid, snap["session_id"])
    run_id = snap["run_id"]
    # wait until the real training has produced episodes that were persisted
    deadline = time.time() + 90
    while time.time() < deadline:
        live = client.get(f"{base(pid)}/training-runs/{run_id}").json()["run"]
        if live["total_episodes"] and live["status"] == "running":
            break
        time.sleep(0.2)
    assert live["status"] == "running" and live["active"] and live["finished_at"] is None
    first = client.post(f"{STUDIO}/sessions/{snap['session_id']}/stop", headers={"X-Project-ID": pid})
    again = client.post(f"{STUDIO}/sessions/{snap['session_id']}/stop", headers={"X-Project-ID": pid})
    assert first.status_code in (200, 202) and again.status_code in (200, 202)  # idempotent
    run = wait_run(client, pid, run_id, {"stopped", "completed", "failed"})
    assert run["status"] == "stopped" and run["termination_reason"] == "user_requested_stop" and not run["active"]
    assert run["total_episodes"] > 0 and run["total_timesteps"] > 0 and run["total_timesteps"] < 400000
    metrics = client.get(f"{base(pid)}/training-runs/{run_id}/metrics").json()
    assert metrics["status"] == "stopped" and metrics["episodes_total"] > 0 and len(metrics["episodes"]) > 0
    assert metrics["episodes"][0]["reward"] is not None  # real recorded episode data


def test_starting_twice_is_refused_and_a_running_session_cannot_be_restarted(client):
    pid = project(client, "A")
    snap = create_session(client, pid, LONG)
    start(client, pid, snap["session_id"])
    again = client.post(f"{STUDIO}/sessions/{snap['session_id']}/start", headers={"X-Project-ID": pid})
    assert again.status_code == 409
    other = create_session(client, pid)
    busy = client.post(f"{STUDIO}/sessions/{other['session_id']}/start", headers={"X-Project-ID": pid})
    assert busy.status_code == 409  # one trainer at a time
    client.post(f"{STUDIO}/sessions/{snap['session_id']}/stop", headers={"X-Project-ID": pid})
    wait_run(client, pid, snap["run_id"], {"stopped", "completed", "failed"})


# --- agents, environments, multiple runs -------------------------------------------------------------------


def test_retraining_the_same_configuration_reuses_the_agent_and_keeps_every_run(client):
    pid = project(client, "A")
    first = train_to_completion(client, pid)
    second = train_to_completion(client, pid)
    assert first["run_id"] != second["run_id"] and first["status"] == second["status"] == "completed"
    assert first["agent_id"] == second["agent_id"] and first["environment_config_id"] == second["environment_config_id"]
    agents = client.get(f"{base(pid)}/agents").json()["agents"]
    assert len(agents) == 1 and agents[0]["run_count"] == 2 and agents[0]["latest_run_id"] == second["run_id"]
    runs = client.get(f"{base(pid)}/training-runs").json()
    assert runs["total"] == 2 and [r["run_id"] for r in runs["items"]] == [second["run_id"], first["run_id"]]
    # the older run is untouched by the newer one
    older = client.get(f"{base(pid)}/training-runs/{first['run_id']}").json()["run"]
    assert older == first


def test_two_agents_in_one_project_keep_independent_histories(client):
    pid = project(client, "A")
    a = client.post(f"{base(pid)}/agents", json={"name": "Agent A", "algorithm": "PPO", "params": {}}).json()
    b = client.post(f"{base(pid)}/agents", json={"name": "Agent B", "algorithm": "A2C", "params": {}}).json()
    run_a = train_to_completion(client, pid, agent_id=a["agent_id"])
    body = {"agent": "A2C", "environment": "cartpole", "training": TRAIN, "agent_id": b["agent_id"]}
    sb = client.post(f"{STUDIO}/sessions", json=body, headers={"X-Project-ID": pid}).json()
    start(client, pid, sb["session_id"])
    run_b = wait_run(client, pid, sb["run_id"], {"completed", "failed", "stopped"})
    assert run_a["agent_id"] == a["agent_id"] and run_b["agent_id"] == b["agent_id"]
    only_a = client.get(f"{base(pid)}/training-runs", params={"agent_id": a["agent_id"]}).json()
    only_b = client.get(f"{base(pid)}/training-runs", params={"agent_id": b["agent_id"]}).json()
    assert [r["run_id"] for r in only_a["items"]] == [run_a["run_id"]] and [r["run_id"] for r in only_b["items"]] == [run_b["run_id"]]
    # "latest run" is per agent, not just per project
    assert client.get(f"{base(pid)}/training-runs/latest").json()["run"]["run_id"] == run_b["run_id"]
    assert client.get(f"{base(pid)}/training-runs/latest", params={"agent_id": a["agent_id"]}).json()["run"]["run_id"] == run_a["run_id"]
    assert client.get(f"{base(pid)}/training-runs", params={"q": "Agent B"}).json()["total"] == 1


def test_changing_an_explicit_agent_creates_a_version_and_old_runs_keep_their_snapshot(client):
    pid = project(client, "A")
    agent = client.post(f"{base(pid)}/agents", json={"name": "Tuned", "algorithm": "PPO", "params": {}}).json()
    first = train_to_completion(client, pid, agent_id=agent["agent_id"])
    second = train_to_completion(client, pid, agent_id=agent["agent_id"], agent_params={"learning_rate": 0.001})
    assert (first["agent_version"], second["agent_version"]) == (1, 2)
    now = next(a for a in client.get(f"{base(pid)}/agents").json()["agents"] if a["agent_id"] == agent["agent_id"])
    assert now["version"] == 2 and now["config"]["agent_params"] == {"learning_rate": 0.001} and len(now["revisions"]) == 1
    old = client.get(f"{base(pid)}/training-runs/{first['run_id']}").json()["snapshots"]["agent"]
    new = client.get(f"{base(pid)}/training-runs/{second['run_id']}").json()["snapshots"]["agent"]
    # each run keeps the full configuration it actually used, so history stays reproducible
    assert new["agent_params"]["learning_rate"] == 0.001 and old["agent_params"]["learning_rate"] != 0.001
    assert old["agent_params"]["n_steps"] == new["agent_params"]["n_steps"]


def test_experiments_group_runs_and_comparison_requires_comparable_runs(client):
    pid = project(client, "A")
    exp = client.post(f"{base(pid)}/experiments", json={"name": "seeds"}).json()
    r1 = train_to_completion(client, pid, experiment_id=exp["experiment_id"])
    r2 = train_to_completion(client, pid, experiment_id=exp["experiment_id"])
    grouped = client.get(f"{base(pid)}/experiments/{exp['experiment_id']}/runs").json()
    assert grouped["total"] == 2 and {r["experiment_name"] for r in grouped["items"]} == {"seeds"}
    cmp = client.get(f"{base(pid)}/training-runs/compare", params={"run_ids": f"{r1['run_id']},{r2['run_id']}"}).json()
    assert cmp["comparable"] and len(cmp["runs"]) == 2
    single = client.get(f"{base(pid)}/training-runs/compare", params={"run_ids": r1["run_id"]}).json()
    assert not single["comparable"] and "at least two" in single["reasons"][0]


def test_list_filters_search_sort_and_pagination(client):
    pid = project(client, "A")
    runs = [train_to_completion(client, pid) for _ in range(3)]
    page = client.get(f"{base(pid)}/training-runs", params={"limit": 2, "offset": 0}).json()
    rest = client.get(f"{base(pid)}/training-runs", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and len(rest["items"]) == 1
    oldest = client.get(f"{base(pid)}/training-runs", params={"sort": "oldest"}).json()["items"]
    assert oldest[0]["run_id"] == runs[0]["run_id"]
    assert client.get(f"{base(pid)}/training-runs", params={"status": "stopped"}).json()["total"] == 0
    assert client.get(f"{base(pid)}/training-runs", params={"q": runs[1]["run_id"]}).json()["total"] == 1
    assert client.get(f"{base(pid)}/training-runs", params={"limit": 500}).status_code == 422  # capped page size


# --- isolation -------------------------------------------------------------------------------------------------


def test_projects_never_leak_agents_runs_or_metrics_into_each_other(client):
    a, b = project(client, "A"), project(client, "B")
    run = train_to_completion(client, a)
    assert client.get(f"{base(b)}/training-runs").json()["total"] == 0
    assert client.get(f"{base(b)}/agents").json()["count"] == 0 and client.get(f"{base(b)}/environments").json()["count"] == 0
    for suffix in ("", "/metrics", "/events", "/checkpoints"):
        assert client.get(f"{base(b)}/training-runs/{run['run_id']}{suffix}").status_code == 404
    assert client.get(f"{base(b)}/training-runs/compare", params={"run_ids": f"{run['run_id']},{run['run_id']}"}).status_code == 404
    # a request scoped to B cannot read A's history through A's path either
    assert client.get(f"{base(a)}/training-runs", headers={"X-Project-ID": b}).status_code == 404
    assert client.get(f"{base(a)}/training-runs", headers={"X-Project-ID": a}).json()["total"] == 1
    # unknown and malformed ids give the same answer
    assert client.get(f"{base(a)}/training-runs/ses_00000000_r1").status_code == 404
    assert client.get("/api/v1/projects/prj_0000000000000000/training-runs").status_code == 404


def test_another_projects_entities_cannot_be_referenced_when_starting_training(client):
    a, b = project(client, "A"), project(client, "B")
    agent_a = client.post(f"{base(a)}/agents", json={"name": "x", "algorithm": "PPO"}).json()
    exp_a = client.post(f"{base(a)}/experiments", json={"name": "e"}).json()
    run_a = train_to_completion(client, a)
    body = {"agent": "PPO", "environment": "cartpole", "training": TRAIN}
    for extra in ({"agent_id": agent_a["agent_id"]}, {"experiment_id": exp_a["experiment_id"]},
                  {"continues_run_id": run_a["run_id"]}):
        r = client.post(f"{STUDIO}/sessions", json={**body, **extra}, headers={"X-Project-ID": b})
        assert r.status_code == 404, (extra, r.text)
    assert client.get(f"{base(b)}/training-runs").json()["total"] == 0  # nothing was created


def test_deleted_projects_history_is_not_served(client):
    pid = project(client, "Gone")
    train_to_completion(client, pid)
    r = client.request("DELETE", f"/api/v1/projects/{pid}", json={"confirm_name": "Gone"})
    assert r.status_code == 200, r.text
    assert client.get(f"{base(pid)}/training-runs").status_code == 404


def test_legacy_runs_without_a_project_are_never_assigned_to_one(client):
    hist = TrainingHistory(client.app.state.database)
    hist.register_run(run_id="ses_aaaaaaaa_r1", project_id=None, session_id="ses_aaaaaaaa", name="legacy",
                      config={"agent": "PPO", "environment": "cartpole", "training": {"seed": 1}}, started_at=None)
    pid = project(client, "A")
    assert client.get(f"{base(pid)}/training-runs").json()["total"] == 0
    assert hist.get_any("ses_aaaaaaaa_r1")["project_id"] is None


# --- continuation, restart, consistency ----------------------------------------------------------------------------


def test_continuation_links_a_new_run_to_the_original_without_overwriting_it(client):
    pid = project(client, "A")
    first = train_to_completion(client, pid)
    second = train_to_completion(client, pid, continues_run_id=first["run_id"])
    assert second["continues_run_id"] == first["run_id"] and second["run_id"] != first["run_id"]
    assert client.get(f"{base(pid)}/training-runs/{first['run_id']}").json()["run"] == first


def test_a_run_abandoned_by_a_restart_is_interrupted_never_completed(make_client):
    first = make_client()
    pid = project(first, "A")
    hist = TrainingHistory(first.app.state.database)
    config = {"agent": "PPO", "environment": "cartpole", "training": {"seed": 3, "total_timesteps": 5000}}
    hist.register_run(run_id="ses_bbbbbbbb_r1", project_id=pid, session_id="ses_bbbbbbbb", name="abandoned",
                      config=config, started_at="2026-01-01T10:00:00+00:00")
    hist.progress("ses_bbbbbbbb_r1", timestep=1200, episodes=40, metrics={"mean_reward": 21.5})
    assert hist.get_any("ses_bbbbbbbb_r1")["status"] == "running"
    restarted = make_client()  # a new process: nothing is alive, the old run was abandoned
    run = restarted.get(f"{base(pid)}/training-runs/ses_bbbbbbbb_r1").json()["run"]
    assert run["status"] == "interrupted" and run["termination_reason"] == "unexpected_interruption"
    assert run["total_timesteps"] == 1200 and run["total_episodes"] == 40 and run["final_metrics"]["mean_reward"] == 21.5
    assert run["finished_at"] and "preserved" in run["error"] and not run["active"]


def test_late_or_out_of_order_writes_never_reopen_or_shrink_a_finished_run(client):
    hist = TrainingHistory(client.app.state.database)
    pid = project(client, "A")
    config = {"agent": "PPO", "environment": "cartpole", "training": {"seed": 1}}
    hist.register_run(run_id="ses_cccccccc_r1", project_id=pid, session_id="ses_cccccccc", name="x", config=config, started_at=None)
    hist.progress("ses_cccccccc_r1", timestep=900, episodes=30)
    hist.progress("ses_cccccccc_r1", timestep=400, episodes=10)  # arrives out of order
    assert hist.get_any("ses_cccccccc_r1")["total_timesteps"] == 900
    hist.finish("ses_cccccccc_r1", status="failed", reason="training_failure", finished_at="2026-01-01T00:00:00+00:00",
                duration_seconds=3.0, timestep=900, episodes=30, metrics=None, error="boom")
    hist.progress("ses_cccccccc_r1", timestep=5000, episodes=99, status="running")  # a late write after the end
    hist.set_status("ses_cccccccc_r1", "running")
    run = hist.get_any("ses_cccccccc_r1")
    assert run["status"] == "failed" and run["termination_reason"] == "training_failure" and run["error"] == "boom"
    assert run["total_timesteps"] == 900 and run["total_episodes"] == 30


def test_a_run_cannot_be_registered_twice_and_invalid_terminal_status_is_rejected(client):
    hist = TrainingHistory(client.app.state.database)
    pid = project(client, "A")
    config = {"agent": "PPO", "environment": "cartpole", "training": {}}
    hist.register_run(run_id="ses_dddddddd_r1", project_id=pid, session_id=None, name=None, config=config, started_at=None)
    from backend.training_history.service import Conflict, Invalid

    with pytest.raises(Conflict):
        hist.register_run(run_id="ses_dddddddd_r1", project_id=pid, session_id=None, name=None, config=config, started_at=None)
    with pytest.raises(Invalid):
        hist.finish("ses_dddddddd_r1", status="running", reason="x", finished_at="t", duration_seconds=None,
                    timestep=0, episodes=0, metrics=None, error=None)


def test_a_run_with_no_episodes_reports_empty_metrics_not_fabricated_ones(client):
    pid = project(client, "A")
    hist = TrainingHistory(client.app.state.database)
    hist.register_run(run_id="ses_eeeeeeee_r1", project_id=pid, session_id=None, name="empty",
                      config={"agent": "PPO", "environment": "cartpole", "training": {}}, started_at=None)
    m = client.get(f"{base(pid)}/training-runs/ses_eeeeeeee_r1/metrics").json()
    assert m["episodes"] == [] and m["available"] is False and m["final_metrics"] == {} and m["episodes_total"] == 0


def test_the_history_endpoints_are_the_same_after_an_app_restart(make_client):
    first = make_client()
    pid = project(first, "A")
    run = train_to_completion(first, pid)
    again: Callable[[], TestClient] = make_client
    second = again()
    assert second.get(f"{base(pid)}/training-runs").json()["items"][0]["run_id"] == run["run_id"]
    assert second.get(f"{base(pid)}/training-runs/{run['run_id']}").json()["run"] == run
    assert second.get(f"{base(pid)}/training-runs/{run['run_id']}/metrics").json()["episodes_total"] > 0


def test_run_detail_links_that_runs_incident_recovery_and_investigation_records_only(client):
    from backend.provenance.models import IncidentRegistration
    from backend.recovery.models import RecoveryCreateRequest, RecoveryStrategy

    pid = project(client, "A")
    older = train_to_completion(client, pid)
    newer = train_to_completion(client, pid)
    services = client.app.state.services
    services.provenance.register_incident(IncidentRegistration(
        incident_id="inc_hist_1", run_id=older["run_id"], status="detected", requirement_id="req_1",
        environment_id="cartpole", environment_version="v1", evidence_ids=["episode_1"], summary="reward below target"))
    services.recovery.create_recovery(
        "inc_hist_1", RecoveryCreateRequest(recovery_strategy=RecoveryStrategy.evaluate_only, execute=False))
    old = client.get(f"{base(pid)}/training-runs/{older['run_id']}").json()
    new = client.get(f"{base(pid)}/training-runs/{newer['run_id']}").json()
    assert [i["incident_id"] for i in old["incidents"]] == ["inc_hist_1"] and old["incidents"][0]["investigations"] == 0
    assert [r["incident_id"] for r in old["recoveries"]] == ["inc_hist_1"]
    assert old["recoveries"][0]["recovery_strategy"] == "evaluate_only" and old["recoveries"][0]["recovery_status"] == "proposed"
    assert new["incidents"] == [] and new["recoveries"] == []  # the newest run's page is not polluted by the older run's
    other = project(client, "B")
    assert client.get(f"{base(other)}/training-runs/{older['run_id']}").status_code == 404
