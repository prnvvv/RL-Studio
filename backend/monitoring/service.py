"""Monitoring service for metrics collection."""
from __future__ import annotations

from typing import Any, Dict, List


class MonitoringService:
    def __init__(self) -> None:
        self.metrics: Dict[str, List[Dict[str, Any]]] = {}

    def record_metric(self, name: str, value: Any, **kwargs: Any) -> None:
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append({"value": value, **kwargs})

    def get_metrics(self, name: str) -> List[Dict[str, Any]]:
        return self.metrics.get(name, [])

    def get_all_metrics(self) -> Dict[str, List[Dict[str, Any]]]:
        return dict(self.metrics)


service = MonitoringService()
