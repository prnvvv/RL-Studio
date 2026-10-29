"""Episode metric model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EpisodeMetric:
    episode_id: str
    seed: int
    reward: float
    length: int
    success: bool = False
    timestep: int = 0
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricSummary:
    name: str
    window: int
    denominator: int
    missing_data_policy: str = "drop"
    values: list[float] = field(default_factory=list)
    mean: float = 0.0
    min: float = 0.0
    max: float = 0.0
