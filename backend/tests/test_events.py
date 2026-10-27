import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.monitoring.events import EventEmitter


def test_event_emission_ordering():
    em = EventEmitter(run_id='r1')
    e1 = em.emit_episode_start('e1', 'warehouse', 'warehouse_v1')
    e2 = em.emit_reward('e1', 1, 1.0, 'warehouse_v1')
    e3 = em.emit_episode_end('e1', 'warehouse', 'warehouse_v1', 1.0, 1, success=True)
    assert e1.sequence < e2.sequence < e3.sequence
    assert e1.event_type == 'episode_started'
    assert e2.event_type == 'reward_observed'
    assert e3.event_type == 'episode_ended'
