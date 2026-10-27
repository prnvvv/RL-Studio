import os
import sys
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.environments.config import WarehouseConfig


def test_invalid_configs():
    with pytest.raises(ValueError):
        WarehouseConfig(rows=0, cols=5, start=(0,0), goal=(1,1), obstacles=[], max_episode_steps=10, goal_reward=1.0, collision_penalty=0.1)
    with pytest.raises(ValueError):
        WarehouseConfig(rows=5, cols=5, start=(-1,0), goal=(1,1), obstacles=[], max_episode_steps=10, goal_reward=1.0, collision_penalty=0.1)
    with pytest.raises(ValueError):
        WarehouseConfig(rows=5, cols=5, start=(0,0), goal=(0,0), obstacles=[], max_episode_steps=10, goal_reward=1.0, collision_penalty=0.1)
    with pytest.raises(ValueError):
        WarehouseConfig(rows=2, cols=2, start=(0,0), goal=(1,1), obstacles=[(0,1),(1,0)], max_episode_steps=10, goal_reward=1.0, collision_penalty=0.1)


def test_obstacle_on_start_goal():
    with pytest.raises(ValueError):
        WarehouseConfig(rows=5, cols=5, start=(0,0), goal=(4,4), obstacles=[(0,0)], max_episode_steps=10, goal_reward=1.0, collision_penalty=0.1)
