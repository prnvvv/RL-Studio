import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.environments.config import WarehouseConfig
from backend.environments.warehouse_env import Warehouse2DEnv


def test_seeded_determinism():
    cfg = WarehouseConfig(rows=5, cols=5, start=(0,0), goal=(4,4), obstacles=[], max_episode_steps=10, goal_reward=1.0, step_reward=0.0, collision_penalty=0.1)
    env1 = Warehouse2DEnv(cfg)
    env2 = Warehouse2DEnv(cfg)
    obs1, _ = env1.reset(seed=123)
    obs2, _ = env2.reset(seed=123)
    assert (obs1 == obs2).all()
    for a in [0,1,2,3,0,1]:
        o1,r1,t1,tr1,_ = env1.step(a)
        o2,r2,t2,tr2,_ = env2.step(a)
        assert (o1==o2).all()
        assert r1==r2 and t1==t2 and tr1==tr2
