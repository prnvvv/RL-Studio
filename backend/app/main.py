"""ASGI entrypoint used by ``uvicorn app.main:app`` started inside ``backend/``.

The canonical FastAPI application is built in :mod:`backend.api.app`. This
module only re-exports it so a single app definition serves every start path
(``backend.main:app``, ``backend.app.main:app`` and ``app.main:app``).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow ``uvicorn app.main:app`` from backend/ by putting the repository root
# (parent of the ``backend`` package) on sys.path before importing backend.*.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.api.app import app

__all__ = ["app"]
