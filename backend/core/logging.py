"""Structured logging setup."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "name": record.name,
        }
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging(level: str = "INFO") -> logging.Logger:
    root = logging.getLogger()
    root.handlers = []
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    return root