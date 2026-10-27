"""Canonical RL execution substrate for Self-Healing RL Studio (Person 2).

This package contains the runtime layer: the Gymnasium 2D warehouse-navigation
environment, controlled fault injection, PPO training with a run lifecycle,
atomic checkpointing, and execution-event monitoring.  It produces schema-
validated :mod:`shared.schemas` events for downstream verification (Person 3)
and provenance/recovery (Person 4).

Modules:
- ``config``      : validated warehouse configuration + stable fingerprint
- ``warehouse_env``: the Gymnasium environment
- ``fingerprints``: stable config/agent/run fingerprint helpers
"""

from __future__ import annotations
