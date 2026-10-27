import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest
from backend.environments.config import WarehouseConfig
from backend.training.ppo import PPOTrainer, RunConfig


@pytest.mark.slow
def test_ppo_smoke_small_timesteps():
    cfg = WarehouseConfig(
        rows=4, cols=4,
        start=(0,0), goal=(3,3),
        obstacles=[],
        max_episode_steps=50,
        goal_reward=10.0,
        step_reward=-0.01,
        collision_penalty=0.1,
    )
    rc = RunConfig(run_id='smoke1', config=cfg, seed=123, total_timesteps=256, n_steps=64, batch_size=32)
    trainer = PPOTrainer(rc)
    trainer.start()
    assert trainer.state.status.value in ('completed', 'stopped')
    fps = trainer.fingerprints()
    assert fps['config_fingerprint']
    assert fps['run_fingerprint']
