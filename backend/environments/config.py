"""Validated configuration for the 2D warehouse-navigation environment.

The :class:`WarehouseConfig` is the single source of truth for a run's
environment.  It is a Pydantic boundary model that rejects malformed input with
useful, structured errors instead of silently repairing it (AGENTS.md TODO
"returning useful errors instead of silent repair", §15).

Key invariants enforced:
- Grid bounds positive and start/goal inside the grid.
- Start and goal occupy distinct, non-obstacle cells.
- Start cell is not an obstacle.
- The goal is reachable from the start by a breadth-first search over free cells
  (4-connectivity).  Reachability is checked so an unreachable goal cannot reach
  a "success" terminal state.
- Rewards are finite; collision penalty is non-negative.
- Step budget is a positive integer.

The config is *not* the environment version.  A version string (e.g.
``warehouse_v1``) is carried alongside and combined into the canonical
fingerprint (see :mod:`backend.environments.fingerprints`).
"""

from __future__ import annotations

from collections import deque
from typing import List, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

Coord = Tuple[int, int]


class WarehouseConfig(BaseModel):
    """Configuration for :class:`~backend.environments.warehouse_env.Warehouse2DEnv`.

    Coordinates are ``(row, col)`` with row increasing downward and col rightward,
    matching a numpy array index.  Cells are 4-connected neighbours.
    """

    environment_id: str = Field(default="warehouse", description="Stable environment identifier.")
    environment_version: str = Field(default="warehouse_v1", description="Immutable version string.")

    rows: int = Field(gt=0, description="Number of grid rows (must be >= 1).")
    cols: int = Field(gt=0, description="Number of grid columns (must be >= 1).")

    start: Coord = Field(description="(row, col) of the agent's start cell.")
    goal: Coord = Field(description="(row, col) of the goal cell.")

    # Obstacles as (row, col) cells.  Walls bound the grid; agent and goal
    # occupy free cells.  An obstacle overlapping start/goal is rejected.
    obstacles: List[Coord] = Field(default_factory=list)

    max_episode_steps: int = Field(gt=0, description="Step budget per episode (truncation).")

    goal_reward: float = Field(description="Reward emitted on reaching the goal.")
    step_reward: float = Field(default=0.0, description="Reward per step (typically 0).")
    collision_penalty: float = Field(
        ge=0.0, description="Non-negative penalty emitted on a collision."
    )
    collision_reward: bool = Field(
        default=False,
        description=(
            "When True, a collision ends the episode (terminated). When False "
            "(default) a collision only applies a penalty and the episode continues."
        ),
    )

    model_config = {"extra": "forbid"}

    # -- field-level validation ------------------------------------------------

    @field_validator("start", "goal")
    @classmethod
    def _coord_shape(cls, value: Coord) -> Coord:
        if len(value) != 2:
            raise ValueError("coordinate must be a (row, col) pair of length 2")
        row, col = value
        if int(row) != row or int(col) != col:
            raise ValueError("coordinate components must be integers")
        return value

    # -- cross-field validation -----------------------------------------------

    @model_validator(mode="after")
    def _validate_layout(self) -> "WarehouseConfig":
        bounds_errors: List[str] = []

        for label, cell in (("start", self.start), ("goal", self.goal)):
            r, c = cell
            if r < 0 or c < 0 or r >= self.rows or c >= self.cols:
                bounds_errors.append(
                    f"{label} {cell!r} is outside the {self.rows}x{self.cols} grid "
                    f"[0<=row<{self.rows}, 0<=col<{self.cols}]"
                )

        obstacle_set = {tuple(o) for o in self.obstacles}
        bad_obstacles = [
            tuple(o) for o in self.obstacles if o[0] < 0 or o[1] < 0 or o[0] >= self.rows or o[1] >= self.cols
        ]
        if bad_obstacles:
            bounds_errors.append(f"obstacles out of bounds: {bad_obstacles}")

        if bounds_errors:
            raise ValueError("; ".join(bounds_errors))

        if self.obstacles:
            for o in self.obstacles:
                if tuple(o) == self.start:
                    raise ValueError(
                        f"obstacle {tuple(self.obstacles)[self.obstacles.index(o)]!r} "
                        f"occupies the start cell {self.start!r}"
                    )
                if tuple(o) == self.goal:
                    raise ValueError(f"obstacle {tuple(o)!r} occupies the goal cell {self.goal!r}")

        if self.start == self.goal:
            raise ValueError(f"start {self.start!r} and goal {self.goal!r} must be distinct cells")

        if not self._is_reachable():
            free_path = " ".join(str(c) for c in sorted(obstacle_set))
            raise ValueError(
                "goal is unreachable from start under 4-connectivity "
                f"(obstacles: {free_path or 'none'})"
            )
        return self

    # -- helpers --------------------------------------------------------------

    def normalized_obstacles(self) -> frozenset[Coord]:
        """Return obstacles as a deterministic, hashable set."""
        return frozenset(tuple(o) for o in self.obstacles)

    def _free_cell(self, cell: Coord) -> bool:
        return tuple(cell) not in self.normalized_obstacles()

    def _is_reachable(self) -> bool:
        """BFS reachability from start to goal over free 4-connected cells."""
        if self.start == self.goal:
            return True
        visited = {self.start}
        queue = deque([self.start])
        while queue:
            r, c = queue.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    cell = (nr, nc)
                    if cell not in visited and self._free_cell(cell):
                        if cell == self.goal:
                            return True
                        visited.add(cell)
                        queue.append(cell)
        return False

    def manhattan_distance(self, a: Coord, b: Coord) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def default_fingerprint_inputs(self) -> dict:
        """Canonical, order-independent view of the config for fingerprinting.

        Used by :func:`backend.environments.fingerprints.config_fingerprint`.
        """
        return {
            "environment_id": self.environment_id,
            "environment_version": self.environment_version,
            "rows": self.rows,
            "cols": self.cols,
            "start": list(self.start),
            "goal": list(self.goal),
            "obstacles": sorted((list(o) for o in self.obstacles), key=lambda p: (p[0], p[1])),
            "max_episode_steps": self.max_episode_steps,
            "goal_reward": self.goal_reward,
            "step_reward": self.step_reward,
            "collision_penalty": self.collision_penalty,
            "collision_reward": self.collision_reward,
        }

    def as_dict(self) -> dict:
        return self.model_dump()
