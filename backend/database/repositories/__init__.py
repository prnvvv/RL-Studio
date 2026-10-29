"""Repository functions for Person 4 persistence.

Repositories accept a connection supplied by ``Database.read``/``Database.write``
and never open transactions themselves.  Services own transaction boundaries.
"""

from . import (
    artifacts,
    audit,
    evaluations,
    impacts,
    incidents,
    locks,
    provenance,
    recoveries,
    runs,
)

__all__ = [
    "artifacts",
    "audit",
    "evaluations",
    "impacts",
    "incidents",
    "locks",
    "provenance",
    "recoveries",
    "runs",
]
