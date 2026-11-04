"""Fixtures: a real app over one isolated data root (call the factory twice to simulate a restart)."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.studio.manager import manager


@pytest.fixture
def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], TestClient]]:
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("RL_STUDIO_DATA_ROOT", str(tmp_path / "var"))
    opened: list[TestClient] = []

    def factory() -> TestClient:
        client = TestClient(create_app())
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for session in list(manager._sessions.values()):
        with contextlib.suppress(Exception):
            session.stop()
        thread = getattr(session, "_thread", None)
        if thread is not None:
            thread.join(timeout=20)
    manager._sessions.clear()
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[[], TestClient]) -> TestClient:
    return make_client()
