"""Runtime controls: knobs the API turns while a session is running.

The training thread and the API/WebSocket threads share one ``RuntimeControls``
per session. Everything here is thread-safe and bounded; wrappers (see
``wrappers.py``) read it on every environment step.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from typing import Any

import gymnasium as gym

from backend.database.exceptions import ValidationError

HUMAN_WAIT_SLICE_S = 0.05


def validate_action(space: gym.Space, action: Any) -> int | list[float]:
    """Check a manually supplied action against the real action space."""
    if isinstance(space, gym.spaces.Discrete):
        if isinstance(action, bool) or not isinstance(action, int) or not 0 <= action < int(space.n):
            raise ValidationError(
                "Invalid action",
                details={"errors": [{"field": "action", "message": f"must be an integer from 0 to {int(space.n) - 1}"}]},
            )
        return int(action)
    if isinstance(space, gym.spaces.Box):
        size = int(math.prod(space.shape))
        ok = (
            isinstance(action, list)
            and len(action) == size
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in action)
        )
        if not ok:
            raise ValidationError(
                "Invalid action",
                details={"errors": [{"field": "action", "message": f"must be a list of {size} finite numbers"}]},
            )
        low, high = space.low.reshape(-1), space.high.reshape(-1)
        return [float(min(max(v, float(lo)), float(hi))) for v, lo, hi in zip(action, low, high, strict=True)]
    raise ValidationError("Manual control is not supported for this action space")


class RuntimeControls:
    """Shared, thread-safe state that wrappers read on every step."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._human = False
        self._pending: int | list[float] | None = None
        self._last: int | list[float] | None = None
        self.human_steps = 0

    # ------------------------------------------------------------- human control

    @property
    def human_active(self) -> bool:
        return self._human

    def set_human(self, active: bool) -> bool:
        """Switch manual control on or off. Returns True when the state changed."""
        with self._cond:
            changed = self._human != active
            self._human = active
            if not active:
                self._pending = None
                self._last = None
            self._cond.notify_all()
            return changed

    def submit_action(self, action: int | list[float]) -> None:
        with self._cond:
            self._pending = action
            self._last = action
            self._cond.notify_all()

    def wait_action(self, sticky: bool, abort: Callable[[], bool]) -> int | list[float] | None:
        """Block until a human action is available.

        ``sticky`` environments (continuous balancing tasks) keep applying the
        last action until a new one arrives. Others consume one action per step.
        Returns None when control was released or the run is stopping.
        """
        with self._cond:
            while self._human and not abort():
                if self._pending is not None:
                    action, self._pending = self._pending, None
                    return action
                if sticky and self._last is not None:
                    return self._last
                self._cond.wait(HUMAN_WAIT_SLICE_S)
        return None

    def snapshot(self) -> dict[str, Any]:
        return {"human": self._human, "human_steps": self.human_steps}
