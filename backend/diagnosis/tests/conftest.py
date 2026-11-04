"""Fixtures: a real temp database seeded through the real provenance service, and a scripted Meta transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.ai.service import AIService
from backend.api.app import create_app
from backend.database.config import DatabaseConfig
from backend.provenance.models import (
    ArtifactRegistration,
    IncidentRegistration,
    RunRegistration,
)
from backend.verification.storage.sqlite_store import SqliteVerificationStore
from backend.verification.tests.phase3_support import make_ai, responses_ok

RUN = "run_1"
INCIDENT = "incident_1"
VERIFICATION = "verification_1"


class ScriptedWonder:
    """Answers Meta Responses API requests; records each one. ``reply`` is the JSON object the model 'returns'."""

    def __init__(self, reply: dict[str, Any] | str | None = None) -> None:
        self.reply: dict[str, Any] | str = reply if reply is not None else {}
        self.calls: list[dict[str, Any]] = []
        self.fail: Callable[[httpx.Request], httpx.Response] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        if self.fail is not None:
            return self.fail(request)
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return httpx.Response(200, json=responses_ok(text, body["model"], f"resp_{len(self.calls)}"))

    @property
    def user_payload(self) -> dict[str, Any]:
        return json.loads(self.calls[-1]["input"][-1]["content"])["incident_evidence"]


@dataclass
class Env:
    client: TestClient
    config: DatabaseConfig
    wonder: ScriptedWonder
    ai: AIService
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def services(self) -> Any:
        return self.client.app.state.services

    @property
    def database(self) -> Any:
        return self.client.app.state.database


def seed(env: Env, *, verification: bool = True, checkpoints: bool = True, evidence: bool = True) -> None:
    prov = env.services.provenance
    prov.register_run(RunRegistration(run_id=RUN, environment_id="warehouse", environment_version="warehouse_v2",
                                      agent_config_fingerprint="ppo-abc"))
    if checkpoints:
        for aid, cid, step in (("artifact_cp_10", "checkpoint_10", 10), ("artifact_cp_50", "checkpoint_50", 50)):
            rel = f"{RUN}/{cid}.zip"
            path = env.config.artifact_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(cid.encode())
            prov.register_artifact(ArtifactRegistration(
                artifact_id=aid, run_id=RUN, artifact_type="checkpoint", artifact_path=rel, checkpoint_id=cid,
                timestep=step, environment_version="warehouse_v1" if step < 40 else "warehouse_v2",
                included_state_components=["policy", "optimizer", "rng", "counters"]))
    prov.register_incident(IncidentRegistration(
        incident_id=INCIDENT, run_id=RUN, verification_id=VERIFICATION if verification else None,
        requirement_id="req_1", environment_id="warehouse", environment_version="warehouse_v2",
        source_environment_version="warehouse_v1", corruption_start_timestep=40, corruption_end_timestep=60,
        evidence_ids=["evidence_1"] if evidence else [], summary="reward requirement failed", severity="high"))
    if verification:
        store = SqliteVerificationStore(env.database)
        store.save_verification(
            {"verification_id": VERIFICATION, "run_id": RUN, "overall_status": "fail", "idempotency_key": "k1",
             "requirement_ids": ["req_1"], "output": {}},
            [{"requirement_id": "req_1", "status": "fail", "expected": 200, "actual": 35,
              "evidence_refs": ["episode_7"], "details": {"comparison": ">="}}])


@pytest.fixture
def make_env(tmp_path: Path) -> Callable[..., Env]:
    clients: list[TestClient] = []

    def build(reply: dict[str, Any] | str | None = None, **seed_kwargs: Any) -> Env:
        config = DatabaseConfig.for_tests(tmp_path)
        client = TestClient(create_app(config))
        client.__enter__()
        clients.append(client)
        wonder = ScriptedWonder(reply)
        ai = make_ai(wonder)
        client.app.state.ai_service = ai
        env = Env(client, config, wonder, ai)
        seed(env, **seed_kwargs)
        return env

    yield build
    for c in clients:
        c.__exit__(None, None, None)
