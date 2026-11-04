"""Event-driven workflow steps, disabled unless explicitly enabled.

Manual actions (evaluate from Reports, investigate from Diagnosis) are always available. These hooks only automate the
same service calls:

* ``RL_STUDIO_AUTO_EVALUATE=true``    - when a training run *completes*, evaluate its latest saved policy (no AI, no credits).
* ``RL_STUDIO_AUTO_INVESTIGATE=true`` - when a verification handoff records an incident, request the advisory investigation
  (consumes Meta credits; a missing or failing provider is logged and never affects the incident).

Work runs on a daemon thread so it can never slow or block training or the verification handoff, and every failure is
logged and swallowed: an automation problem must not change a recorded run, verification or incident.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

#: callbacks ``(run_id, status)`` invoked by the training bridge when a run reaches a terminal status
run_completed_hooks: list[Callable[[str, str], None]] = []


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _background(name: str, fn: Callable[[], Any]) -> None:
    def runner() -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - automation must never surface into the caller
            logger.warning("workflow automation %s failed (%s)", name, type(exc).__name__)

    threading.Thread(target=runner, name=f"workflow-{name}", daemon=True).start()


class WorkflowAutomation:
    def __init__(self, *, evaluate: Callable[[str], Any], investigate: Callable[[str], Any]) -> None:
        self._evaluate = evaluate
        self._investigate = investigate
        self.auto_evaluate = _flag("RL_STUDIO_AUTO_EVALUATE")
        self.auto_investigate = _flag("RL_STUDIO_AUTO_INVESTIGATE")

    def install(self) -> None:
        if self.auto_evaluate:
            run_completed_hooks.append(self.on_run_finished)

    def uninstall(self) -> None:
        if self.on_run_finished in run_completed_hooks:
            run_completed_hooks.remove(self.on_run_finished)

    def on_run_finished(self, run_id: str, status: str) -> None:
        if self.auto_evaluate and status == "completed":
            _background("evaluate", lambda: self._evaluate(run_id))

    def wrap_sink(self, sink: Any) -> Any:
        """Return an incident sink that also requests an investigation after each newly recorded incident."""
        if not self.auto_investigate:
            return sink
        automation = self

        class _Sink:
            def record(self, draft: Any) -> dict[str, Any]:
                stored = sink.record(draft)
                incident_id = stored.get("incident_id")
                if incident_id:
                    _background("investigate", lambda: automation._investigate(incident_id))
                return stored

        return _Sink()
