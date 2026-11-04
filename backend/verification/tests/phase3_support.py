"""Shared helpers for the Phase 3 tests.

* ``ScriptedProvider`` replaces the *network* only: the real ``AIService``, task registry, Meta client (OpenAI SDK),
  retry/fallback logic all run, with an ``httpx.MockTransport`` answering for the Meta Responses API. Any test
  using it exercises no live provider - nothing here claims a live Meta call.
* ``trained_run`` trains a real (small) Studio run through the real HTTP API so the evidence is the
  genuine Phase 2 persisted data.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.ai.clients import MetaClient
from backend.ai.service import AIService
from backend.ai.settings import AISettings
from backend.api.app import create_app
from backend.studio.manager import manager
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.studio.tests.test_studio import BASE, _create, _wait
from backend.verification.lifecycle import VerificationLifecycle

SECRET = "meta_test_secret_value_do_not_leak"


def reward_proposal(statement: str, *, op: str | None = ">=", value: Any = 1, **extra: Any) -> dict[str, Any]:
    return {
        "source_statement": statement, "type": "reward", "description": f"final episode reward {op} {value}",
        "criterion": "compare final episode reward", "comparison_operator": op, "expected_value": value, **extra,
    }


def statements_json(*texts: str, contradictions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "statements": [{"text": t, "category": "reward", "clarity": "clear", "reason": "stated"} for t in texts],
        "contradictions": contradictions or [], "summary": "",
    }


class ScriptedProvider:
    """Answers Meta Responses API requests. ``mode`` can switch to failures; every request is logged."""

    def __init__(self, interpretation: dict[str, Any] | None = None, requirements: list[dict[str, Any]] | None = None) -> None:
        self.interpretation = interpretation or statements_json("x")
        self.requirements = requirements or []
        self.mode = "ok"  # ok | down | rate_limit | bad_json | bad_schema
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["input"][0]["content"]
        stage = "intent" if '"statements":[{"text"' in system else "requirements"
        self.calls.append({"stage": stage, "model": body["model"], "auth": request.headers.get("authorization"),
                           "user": body["input"][1]["content"], "role": body["input"][0]["role"]})
        if self.mode == "down":
            return httpx.Response(503, json={"error": "upstream detail that must not leak"})
        if self.mode == "rate_limit":
            return httpx.Response(429, json={"error": "slow down"})
        if self.mode == "bad_json":
            content = "this is not json {"
        elif self.mode == "bad_schema":
            content = json.dumps({"statements": "nope", "requirements": 7})
        else:
            content = json.dumps(self.interpretation if stage == "intent" else {"requirements": self.requirements})
        return httpx.Response(200, json=responses_ok(content, body["model"], f"resp_{len(self.calls)}"))


def responses_ok(text: str, model: str = "muse-spark-1.3", rid: str = "resp_1") -> dict[str, Any]:
    """A minimal, documented-shape Meta Responses API body whose ``output_text`` is ``text``."""
    return {
        "id": rid, "object": "response", "created_at": 0, "model": model, "status": "completed",
        "output": [{"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 10},
    }


def make_ai(handler: Callable[[httpx.Request], httpx.Response], **env: str) -> AIService:
    settings = AISettings.from_env({"MODAL_API_KEY": SECRET, "META_API_MAX_RETRIES": "1", **env})
    client = MetaClient(settings.base_url, settings.api_key, transport=httpx.MockTransport(handler), sleep=lambda _s: None)
    return AIService(settings, client=client)


class ExplodingAI(AIService):
    """Any model call fails the test: used to prove verification needs no AI."""

    def __init__(self) -> None:
        pass

    def run_text(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a model was called during deterministic verification")


@dataclass
class Trained:
    client: TestClient
    run_id: str
    session_id: str
    root: Path

    def lifecycle(self, ai: AIService | None = None, sink: Any = None) -> VerificationLifecycle:
        app = self.client.app
        return VerificationLifecycle(
            database=app.state.database, reader=TrajectoryReader(store_path()),
            provenance=app.state.services.provenance, ai=ai, incident_sink=sink,
        )


TRAINING = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2}


@contextlib.contextmanager
def train_real_run(root: Path) -> Iterator[Trained]:
    """Create the app on isolated data roots, run a real small CartPole training, yield its identifiers."""
    mp = pytest.MonkeyPatch()
    mp.setenv("STUDIO_DATA_DIR", str(root / "studio"))
    mp.setenv("RL_STUDIO_DATA_ROOT", str(root / "var"))
    try:
        with TestClient(create_app()) as client:
            sid = _create(client, training=TRAINING)
            client.post(f"{BASE}/sessions/{sid}/start")
            snap = _wait(client, sid, {"completed", "failed"})
            assert snap["status"] == "completed", snap.get("error")
            yield Trained(client, snap["run_id"], sid, root)
            for session in list(manager._sessions.values()):
                with contextlib.suppress(Exception):
                    session.stop()
                thread = getattr(session, "_thread", None)
                if thread is not None:
                    thread.join(timeout=10)
            manager._sessions.clear()
    finally:
        mp.undo()
