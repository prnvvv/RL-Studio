import os
import sys
import tempfile
import glob
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.training.callbacks import CheckpointCallback
from stable_baselines3 import PPO
from backend.environments.config import WarehouseConfig
from backend.environments.warehouse_env import Warehouse2DEnv
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor


def test_checkpoint_roundtrip_atomic():
    cfg = WarehouseConfig(rows=4, cols=4, start=(0,0), goal=(3,3), obstacles=[], max_episode_steps=20, goal_reward=1.0, step_reward=0.0, collision_penalty=0.1)
    def _init():
        return Monitor(Warehouse2DEnv(cfg))
    env = DummyVecEnv([_init])
    model = PPO('MlpPolicy', env, verbose=0)
    with tempfile.TemporaryDirectory() as td:
        cb = CheckpointCallback(save_freq=1, save_path=td, run_id='r1')
        cb.model = model
        cb.num_timesteps = 10
        cb._save_checkpoint()
        metas = glob.glob(os.path.join(td, '*.meta.json'))
        assert len(metas) == 1
        with open(metas[0]) as f:
            meta = json.load(f)
        assert meta['checkpoint_id']
        assert meta['sha256']
