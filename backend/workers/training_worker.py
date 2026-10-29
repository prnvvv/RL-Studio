"""Training worker for non-blocking execution."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class TrainingWorker:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._results: dict[str, Any] = {}

    def submit(self, run_id: str, fn: Callable[[], Any]) -> str:
        def _run():
            try:
                self._results[run_id] = fn()
            except Exception as e:  # noqa: BLE001
                self._results[run_id] = {"error": str(e)}

        t = threading.Thread(target=_run, daemon=True)
        self._threads[run_id] = t
        t.start()
        return run_id

    def status(self, run_id: str) -> dict[str, Any]:
        t = self._threads.get(run_id)
        if t and t.is_alive():
            return {"run_id": run_id, "status": "running"}
        if run_id in self._results:
            res = self._results[run_id]
            if isinstance(res, dict) and "error" in res:
                return {"run_id": run_id, "status": "failed", "error": res["error"]}
            return {"run_id": run_id, "status": "completed"}
        return {"run_id": run_id, "status": "unknown"}


worker = TrainingWorker()
