import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.environments.config import WarehouseConfig
from backend.environments.warehouse_env import Warehouse2DEnv


def test_warehouse_env_reset_step():
    cfg = WarehouseConfig(
        rows=5, cols=5,
        start=(0,0), goal=(4,4),
        obstacles=[],
        max_episode_steps=50,
        goal_reward=10.0,
        step_reward=-0.01,
        collision_penalty=1.0,
    )
    env = Warehouse2DEnv(cfg)
    obs, info = env.reset(seed=42)
    assert obs.shape == (6,)
    obs, reward, terminated, truncated, info = env.step(1)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
