"""Every documented start path serves the same canonical app, including ``/health``."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("module", ["backend.main", "backend.app.main"])
def test_entrypoints_expose_the_canonical_app_with_a_health_check(module: str) -> None:
    app = importlib.import_module(module).app
    from backend.api.app import app as canonical

    assert set(app.openapi()["paths"]) == set(canonical.openapi()["paths"])
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
