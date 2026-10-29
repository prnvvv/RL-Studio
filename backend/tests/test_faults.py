import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.fault_injection.faults import FaultConfig, FaultInjector, FaultType


def test_reward_scaling_exact_boundary():
    cfg = FaultConfig(fault_type=FaultType.REWARD_SCALING, trigger_step=5, scale=10.0)
    inj = FaultInjector(cfg)
    assert inj.apply_reward_scaling(1.0, 4, 0) == 1.0
    assert inj.apply_reward_scaling(1.0, 5, 0) == 10.0
    assert inj.apply_reward_scaling(1.0, 6, 0) == 1.0


def test_observation_corruption():
    cfg = FaultConfig(fault_type=FaultType.OBSERVATION_CORRUPTION, trigger_step=0, noise_scale=1.0)
    inj = FaultInjector(cfg)
    obs = np.array([1.0, 2.0])
    obs2 = inj.apply_observation_corruption(obs, 0, 0)
    assert obs2.shape == obs.shape
    assert not np.array_equal(obs2, obs)


def test_invalid_termination():
    cfg = FaultConfig(fault_type=FaultType.INVALID_TERMINATION, trigger_step=3)
    inj = FaultInjector(cfg)
    assert inj.apply_termination(False, 2, 0) is False
    assert inj.apply_termination(False, 3, 0) is True
