"""Monitoring service for metrics collection."""
from __future__ import annotations

from typing import Any


class MonitoringService:
    def __init__(self) -> None:
        self.metrics: dict[str, list[dict[str, Any]]] = {}

    def record_metric(self, name: str, value: Any, **kwargs: Any) -> None:
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append({"value": value, **kwargs})

    def get_metrics(self, name: str) -> list[dict[str, Any]]:
        return self.metrics.get(name, [])

    def get_all_metrics(self) -> dict[str, list[dict[str, Any]]]:
        return dict(self.metrics)


service = MonitoringService()
