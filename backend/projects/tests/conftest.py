from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app


@pytest.fixture
def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], TestClient]]:
    """Factory for app instances over one isolated data root (call twice to simulate a restart)."""
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("RL_STUDIO_DATA_ROOT", str(tmp_path / "var"))
    opened: list[TestClient] = []

    def factory() -> TestClient:
        client = TestClient(create_app())
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[[], TestClient]) -> TestClient:
    return make_client()
