"""Policy introspection for the live "agent brain" view.

Everything here is computed from the real policy networks on the real current
observation: action probabilities for actor-critic agents (PPO/A2C and uploaded
actor-critic policies), Q-values for DQN. Nothing is estimated or simulated.
"""

from __future__ import annotations

from typing import Any

import numpy as np

MAX_GRID_CELLS = 400
GRID_REFRESH_FRAMES = 6


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / exp.sum()


def _evaluate(policy: Any, observations: np.ndarray) -> dict[str, Any] | None:
    """Per-row action preferences for a batch of observations, or None for unsupported policies."""
    import torch

    with torch.no_grad():
        tensor, _ = policy.obs_to_tensor(observations)
        if hasattr(policy, "q_net"):  # DQN-style
            q = policy.q_net(tensor).cpu().numpy()
            return {"kind": "q", "q": q, "probs": np.apply_along_axis(_softmax, 1, q)}
        if hasattr(policy, "get_distribution"):
            dist = policy.get_distribution(tensor).distribution
            if hasattr(dist, "probs"):  # categorical
                probs = dist.probs.cpu().numpy()
                return {"kind": "probs", "probs": probs}
            if hasattr(dist, "mean"):  # diagonal Gaussian (continuous actions)
                return {"kind": "gaussian", "mean": dist.mean.cpu().numpy(), "std": dist.stddev.cpu().numpy()}
    return None


def _round(values: np.ndarray) -> list[float]:
    return [round(float(v), 4) for v in np.asarray(values).reshape(-1)]


def compute_brain(policy: Any, obs: Any, executed: Any = None) -> dict[str, Any] | None:
    """What the agent "thinks" at this observation. None when the policy cannot be introspected."""
    if policy is None or obs is None:
        return None
    result = _evaluate(policy, np.asarray(obs, dtype=np.float32).reshape(1, -1))
    if result is None:
        return None
    if result["kind"] == "gaussian":
        return {"kind": "gaussian", "mean": _round(result["mean"][0]), "std": _round(result["std"][0]), "executed": executed}
    brain: dict[str, Any] = {"kind": result["kind"], "probs": _round(result["probs"][0]), "executed": executed}
    if result["kind"] == "q":
        brain["q"] = _round(result["q"][0])
        brain["probs_from"] = "softmax(q)"
    brain["greedy"] = int(np.argmax(result["probs"][0]))
    return brain


def free_cells(scene: dict[str, Any]) -> list[tuple[int, int]]:
    obstacles = {tuple(o) for o in scene["obstacles"]}
    return [(r, c) for r in range(scene["rows"]) for c in range(scene["cols"]) if (r, c) not in obstacles]


def compute_grid_brain(policy: Any, scene: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The policy's preference at every free grid cell (warehouse-style environments).

    Observations follow the warehouse layout ``[row, col, goal_row, goal_col,
    distance_to_goal, obstacle_count]`` with the goal and obstacles fixed.
    """
    if policy is None or not {"rows", "cols", "goal", "obstacles"} <= scene.keys():
        return None
    cells = free_cells(scene)
    if not cells or len(cells) > MAX_GRID_CELLS:
        return None
    gr, gc = scene["goal"]
    count = float(len(scene["obstacles"]))
    batch = np.array([[r, c, gr, gc, abs(r - gr) + abs(c - gc), count] for r, c in cells], dtype=np.float32)
    result = _evaluate(policy, batch)
    if result is None or result["kind"] == "gaussian":
        return None
    return [
        {"row": r, "col": c, "probs": _round(result["probs"][i]), "greedy": int(np.argmax(result["probs"][i]))}
        for i, (r, c) in enumerate(cells)
    ]
