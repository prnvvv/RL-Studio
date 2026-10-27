import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.training.ppo import PPOTrainer, RunConfig, RunStatus
from backend.environments.config import WarehouseConfig


def test_lifecycle_idempotent_stop():
    cfg = WarehouseConfig(rows=4, cols=4, start=(0,0), goal=(3,3), obstacles=[], max_episode_steps=10, goal_reward=1.0, step_reward=0.0, collision_penalty=0.1)
    rc = RunConfig(run_id='r1', config=cfg, seed=123, total_timesteps=64, n_steps=64)
    trainer = PPOTrainer(rc)
    assert trainer.state.status == RunStatus.CREATED
    trainer.stop(idempotent=True)
    trainer.stop(idempotent=True)
    assert trainer.state.stop_requested
