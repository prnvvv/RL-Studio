import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.monitoring.metrics import EpisodeMetrics, RollingMetrics


def test_episode_and_rolling_metrics():
    ep = EpisodeMetrics(episode_id='e1', run_id='r1')
    ep.add_step(1.0, collision=False)
    ep.add_step(-0.01, collision=True)
    ep.end(success=True)
    s = ep.summary()
    assert s['length'] == 2
    assert s['collisions'] == 1
    assert s['success'] is True

    rm = RollingMetrics(window=10)
    rm.add_episode(5.0, 10, 1, True)
    rm.add_episode(1.0, 20, 2, False)
    agg = rm.aggregate()
    assert agg['count'] == 2
    assert agg['success_rate'] == 0.5
    assert 'collision_rate' in agg
