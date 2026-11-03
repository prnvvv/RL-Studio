"""Shared pytest fixtures for the studio API tests."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.studio.manager import manager


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("RL_STUDIO_DATA_ROOT", str(tmp_path / "var"))
    with TestClient(create_app()) as test_client:
        yield test_client
    for session in list(manager._sessions.values()):
        with contextlib.suppress(Exception):
            session.stop()
    manager._sessions.clear()
