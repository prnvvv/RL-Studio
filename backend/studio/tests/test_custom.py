"""Custom model / environment upload: validation, security, and real inference runs."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import gymnasium as gym
import pytest
import torch
from fastapi.testclient import TestClient
from stable_baselines3 import A2C, DQN, PPO

from backend.studio import custom
from backend.studio.envs import ENVIRONMENTS

from .test_persistence import _all_steps
from .test_studio import BASE, _create, _wait

FAST = {"total_timesteps": 1000, "simulation_speed": 0}


def _model_bytes(cls: Any, env: gym.Env, **kwargs: Any) -> bytes:
    buffer = io.BytesIO()
    cls("MlpPolicy", env, verbose=0, seed=1, device="cpu", **kwargs).save(buffer)
    return buffer.getvalue()


def _cartpole_env() -> gym.Env:
    return gym.make("CartPole-v1")


def _warehouse_env() -> gym.Env:
    definition = ENVIRONMENTS["warehouse"]
    return definition.make({p.key: p.default for p in definition.params}, 0)


def _upload(client: TestClient, data: bytes, filename: str = "policy.zip", **params: str) -> Any:
    return client.post(f"{BASE}/models/upload", params={"filename": filename, **params}, content=data)


@pytest.fixture()
def ppo_zip() -> bytes:
    return _model_bytes(PPO, _cartpole_env())


def test_uploading_each_sb3_algorithm_extracts_real_metadata(client: TestClient) -> None:
    expected = {
        "PPO": (_model_bytes(PPO, _cartpole_env()), "PPO"),
        "A2C": (_model_bytes(A2C, _cartpole_env()), "A2C"),
        "DQN": (_model_bytes(DQN, _cartpole_env(), buffer_size=100), "DQN"),
    }
    for label, (data, algorithm) in expected.items():
        response = _upload(client, data, f"{label}.zip")
        assert response.status_code == 201, response.text
        model = response.json()["model"]
        assert model["algorithm"] == algorithm and model["obs_dim"] == 4
        assert model["action_type"] == "discrete" and model["action_dim"] == 2
        assert model["format"] == "zip" and len(model["sha256"]) == 64 and "stored_as" not in model
    assert len(client.get(f"{BASE}/models").json()["models"]) == 3


def test_catalog_lists_uploaded_model_with_derived_compatibility(client: TestClient, ppo_zip: bytes) -> None:
    key = _upload(client, ppo_zip, name="My policy").json()["model"]["key"]
    catalog = client.get(f"{BASE}/catalog").json()
    agent = next(a for a in catalog["agents"] if a["key"] == key)
    assert agent["kind"] == "custom" and agent["name"] == "My policy" and agent["params"] == []
    assert agent["compatible_environments"] == ["cartpole"]
    cartpole = next(e for e in catalog["environments"] if e["key"] == "cartpole")
    assert key in cartpole["compatible_agents"]
    assert key not in next(e for e in catalog["environments"] if e["key"] == "warehouse")["compatible_agents"]
    assert {a["key"] for a in catalog["agents"] if a["kind"] == "builtin"} == {"PPO", "A2C", "DQN"}


def test_duplicate_upload_is_idempotent(client: TestClient, ppo_zip: bytes) -> None:
    first = _upload(client, ppo_zip)
    second = _upload(client, ppo_zip, "renamed.zip")
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["duplicate"] is True and second.json()["model"]["model_id"] == first.json()["model"]["model_id"]


def test_uploaded_model_runs_real_inference_and_persists_the_trajectory(client: TestClient, ppo_zip: bytes) -> None:
    key = _upload(client, ppo_zip).json()["model"]["key"]
    sid = _create(client, agent=key, training=FAST)
    assert client.get(f"{BASE}/sessions/{sid}").json()["mode"] == "inference"
    client.post(f"{BASE}/sessions/{sid}/start")
    snap = _wait(client, sid, {"completed", "failed"})
    assert snap["status"] == "completed", snap["error"]
    assert snap["progress"]["timestep"] == 1000 and snap["episodes"]
    assert snap["updates"] == [] and snap["checkpoints"] == []  # nothing is learned
    run = client.get(f"{BASE}/runs/{snap['run_id']}").json()
    assert run["mode"] == "inference" and run["agent"] == key and run["step_count"] == 1000
    first_steps = _all_steps(client, snap["run_id"])
    assert all(s["observation"] is not None and s["action"] in (0, 1) for s in first_steps)

    # A deterministic policy on a seeded environment repeats itself exactly.
    client.post(f"{BASE}/sessions/{sid}/reset")
    client.post(f"{BASE}/sessions/{sid}/start")
    again = _wait(client, sid, {"completed", "failed"})
    second_steps = _all_steps(client, again["run_id"])
    assert [s["action"] for s in second_steps] == [s["action"] for s in first_steps]


def test_incompatible_environment_fails_gracefully_with_a_clear_error(client: TestClient, ppo_zip: bytes) -> None:
    key = _upload(client, ppo_zip).json()["model"]["key"]
    response = client.post(f"{BASE}/sessions", json={"agent": key, "environment": "warehouse", "training": FAST})
    assert response.status_code == 422
    message = response.json()["error"]["details"]["errors"][0]["message"]
    assert "expects 4 observation values" in message and "Warehouse" in message


def test_model_for_warehouse_runs_on_warehouse(client: TestClient) -> None:
    key = _upload(client, _model_bytes(PPO, _warehouse_env()), "wh.zip").json()["model"]["key"]
    sid = _create(client, agent=key, environment="warehouse", training={**FAST, "total_timesteps": 1000})
    client.post(f"{BASE}/sessions/{sid}/start")
    assert _wait(client, sid, {"completed", "failed"})["status"] == "completed"


@pytest.mark.parametrize(
    "filename, fragment",
    [("policy.pkl", "Pickle"), ("policy.pickle", "Pickle"), ("policy.onnx", "ONNX"), ("policy.exe", "Unsupported"), ("policy", "Unsupported")],
)
def test_unsupported_formats_are_refused_with_a_reason(client: TestClient, filename: str, fragment: str) -> None:
    response = _upload(client, b"data", filename)
    assert response.status_code == 422 and fragment in response.json()["error"]["message"]


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not a zip at all",
        _zip({"readme.txt": b"hi"}),
        _zip({"../escape": b"x", "policy.pth": b"x", "data": b"{}"}),
        _zip({"policy.pth": b"garbage", "data": b"{}"}),
        _zip({"policy.pth": b"garbage", "data": b"not json"}),
    ],
)
def test_malformed_archives_are_rejected(client: TestClient, data: bytes) -> None:
    assert _upload(client, data).status_code == 422
    assert client.get(f"{BASE}/models").json()["models"] == []


class _Evil:
    marker = ""

    def __reduce__(self) -> tuple[Any, ...]:
        return (Path(self.marker).write_text, ("pwned",))


def test_pickled_code_in_weights_is_never_executed(client: TestClient, tmp_path: Path) -> None:
    marker = tmp_path / "pwned.txt"
    _Evil.marker = str(marker)
    buffer = io.BytesIO()
    torch.save(_Evil(), buffer)
    assert _upload(client, buffer.getvalue(), "evil.pt").status_code == 422
    assert _upload(client, _zip({"policy.pth": buffer.getvalue(), "data": b"{}"})).status_code == 422
    assert not marker.exists()


def test_state_dict_pt_upload_is_accepted(client: TestClient) -> None:
    model = PPO("MlpPolicy", _cartpole_env(), verbose=0)
    buffer = io.BytesIO()
    torch.save(model.policy.state_dict(), buffer)
    response = _upload(client, buffer.getvalue(), "weights.pt")
    assert response.status_code == 201, response.text
    assert response.json()["model"]["format"] == "pt" and response.json()["model"]["obs_dim"] == 4


def test_inconsistent_tensors_are_rejected(client: TestClient) -> None:
    state = PPO("MlpPolicy", _cartpole_env(), verbose=0).policy.state_dict()
    state["action_net.weight"] = torch.zeros(2, 7)  # head no longer matches the network
    buffer = io.BytesIO()
    torch.save(state, buffer)
    assert _upload(client, buffer.getvalue(), "bad.pt").status_code == 422
    state = {k: v.clone() for k, v in PPO("MlpPolicy", _cartpole_env(), verbose=0).policy.state_dict().items()}
    state["mlp_extractor.policy_net.0.weight"][0, 0] = float("nan")
    buffer = io.BytesIO()
    torch.save(state, buffer)
    assert _upload(client, buffer.getvalue(), "nan.pt").status_code == 422


def test_oversized_uploads_are_refused(client: TestClient, ppo_zip: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(custom, "MAX_MODEL_BYTES", 1000)
    response = _upload(client, ppo_zip)
    assert response.status_code == 413
    assert not list(custom.incoming_dir().glob("*"))  # quarantine is cleaned up


def test_tampered_stored_file_fails_the_run_instead_of_loading(client: TestClient, ppo_zip: bytes) -> None:
    model = _upload(client, ppo_zip).json()["model"]
    sid = _create(client, agent=model["key"], training=FAST)
    (custom.models_dir() / model["model_id"] / "model.zip").write_bytes(b"tampered")
    client.post(f"{BASE}/sessions/{sid}/start")
    snap = _wait(client, sid, {"failed", "completed"})
    assert snap["status"] == "failed" and "no longer matches" in snap["error"]


def test_deleting_models(client: TestClient, ppo_zip: bytes) -> None:
    model = _upload(client, ppo_zip).json()["model"]
    slow = {"total_timesteps": 200_000, "simulation_speed": 2}
    sid = _create(client, agent=model["key"], training=slow)
    client.post(f"{BASE}/sessions/{sid}/start")
    assert client.delete(f"{BASE}/models/{model['model_id']}").status_code == 409  # in use
    client.post(f"{BASE}/sessions/{sid}/stop")
    _wait(client, sid, {"stopped"})
    assert client.delete(f"{BASE}/models/{model['model_id']}").status_code == 200
    assert client.delete(f"{BASE}/models/{model['model_id']}").status_code == 404
    assert client.delete(f"{BASE}/models/..%2F..").status_code == 404
    gone = client.post(f"{BASE}/sessions", json={"agent": model["key"], "environment": "cartpole"})
    assert gone.status_code == 422


# ------------------------------------------------------------------ environments

LAYOUT = {"name": "My grid", "rows": 4, "cols": 5, "start": [0, 0], "goal": [3, 4], "obstacles": [[1, 1], [2, 3]]}


def _upload_env(client: TestClient, layout: Any) -> Any:
    return client.post(f"{BASE}/environments/upload", content=json.dumps(layout))


def test_custom_grid_environment_is_listed_and_trainable(client: TestClient) -> None:
    response = _upload_env(client, LAYOUT)
    assert response.status_code == 201, response.text
    key = response.json()["environment"]["key"]
    catalog = client.get(f"{BASE}/catalog").json()
    entry = next(e for e in catalog["environments"] if e["key"] == key)
    assert entry["kind"] == "custom" and entry["name"] == "My grid" and entry["renderer"] == "grid_maze"
    assert entry["default_scene"]["rows"] == 4 and entry["default_scene"]["obstacles"] == [[1, 1], [2, 3]]
    assert {"PPO", "A2C", "DQN"} <= set(entry["compatible_agents"])
    assert {p["key"] for p in entry["params"]} >= {"goal_reward", "max_episode_steps"}

    sid = _create(client, agent="A2C", environment=key, training={**FAST, "total_timesteps": 1000, "checkpoint_every": 0, "eval_every": 0})
    snap = client.get(f"{BASE}/sessions/{sid}").json()
    assert snap["scene"]["cols"] == 5 and snap["name"] == "A2C on My grid"
    client.post(f"{BASE}/sessions/{sid}/start")
    assert _wait(client, sid, {"completed", "failed"})["status"] == "completed"
    assert _upload_env(client, LAYOUT).status_code == 200  # same layout is a no-op


@pytest.mark.parametrize(
    "layout",
    [
        {**LAYOUT, "obstacles": [[0, 1], [1, 0]]},  # goal unreachable
        {**LAYOUT, "goal": [9, 9]},  # outside the grid
        {**LAYOUT, "start": [3, 4]},  # start == goal
        {**LAYOUT, "rows": 500, "cols": 500},  # too big
        {**LAYOUT, "extra": 1},  # unknown field
        {**LAYOUT, "goal": "far"},  # wrong type
        {**LAYOUT, "obstacles": [[0, 0]]},  # obstacle on the start cell
        [1, 2, 3],  # not an object
    ],
)
def test_invalid_layouts_are_rejected(client: TestClient, layout: Any) -> None:
    response = _upload_env(client, layout)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"]["errors"]


def test_environment_upload_rejects_bad_json_and_huge_bodies(client: TestClient) -> None:
    assert client.post(f"{BASE}/environments/upload", content=b"{nope").status_code == 422
    assert client.post(f"{BASE}/environments/upload", content=b" " * 70_000).status_code == 413


def test_custom_model_can_target_a_custom_environment(client: TestClient) -> None:
    key = _upload_env(client, LAYOUT).json()["environment"]["key"]
    env = ENVIRONMENTS["warehouse"].make({p.key: p.default for p in ENVIRONMENTS["warehouse"].params}, 0)
    model_key = _upload(client, _model_bytes(PPO, env), "grid.zip").json()["model"]["key"]
    entry = next(e for e in client.get(f"{BASE}/catalog").json()["environments"] if e["key"] == key)
    assert model_key in entry["compatible_agents"]
    sid = _create(client, agent=model_key, environment=key, training=FAST)
    client.post(f"{BASE}/sessions/{sid}/start")
    assert _wait(client, sid, {"completed", "failed"})["status"] == "completed"


def test_deleting_environments(client: TestClient) -> None:
    env_id = _upload_env(client, LAYOUT).json()["environment"]["env_id"]
    assert client.delete(f"{BASE}/environments/{env_id}").status_code == 200
    assert client.delete(f"{BASE}/environments/{env_id}").status_code == 404
    assert all(e["kind"] == "builtin" for e in client.get(f"{BASE}/catalog").json()["environments"])
