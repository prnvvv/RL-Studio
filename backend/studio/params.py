"""Declarative, validated parameter specifications.

Every configurable value the studio exposes is described by a ``ParamSpec`` so
the same definition drives the catalog shown in the UI and the server-side
validation. Unknown keys are rejected (fail closed) instead of being ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from backend.database.exceptions import ValidationError


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    kind: str  # "int" | "float" | "choice" | "bool"
    default: Any
    help: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "help": self.help,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "options": list(self.options),
        }


def _coerce(spec: ParamSpec, value: Any) -> Any:
    if spec.kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError("must be true or false")
    if spec.kind == "choice":
        if isinstance(value, str) and value in spec.options:
            return value
        raise ValueError(f"must be one of {list(spec.options)}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")  # noqa: TRY004 - caller maps ValueError to a field error
    if not math.isfinite(float(value)):
        raise ValueError("must be finite")
    if spec.kind == "int":
        if int(value) != value:
            raise ValueError("must be an integer")
        number: Any = int(value)
    else:
        number = float(value)
    if spec.min is not None and number < spec.min:
        raise ValueError(f"must be >= {spec.min:g}")
    if spec.max is not None and number > spec.max:
        raise ValueError(f"must be <= {spec.max:g}")
    return number


def validate_params(
    specs: tuple[ParamSpec, ...],
    values: dict[str, Any] | None,
    *,
    scope: str,
) -> dict[str, Any]:
    """Return ``values`` with defaults applied, or raise a structured error."""
    values = dict(values or {})
    by_key = {spec.key: spec for spec in specs}
    errors: list[dict[str, str]] = []
    for key in values:
        if key not in by_key:
            errors.append({"field": f"{scope}.{key}", "message": "unknown parameter"})
    result: dict[str, Any] = {}
    for spec in specs:
        if spec.key not in values:
            result[spec.key] = spec.default
            continue
        try:
            result[spec.key] = _coerce(spec, values[spec.key])
        except ValueError as exc:
            errors.append({"field": f"{scope}.{spec.key}", "message": str(exc)})
    if errors:
        raise ValidationError("Invalid configuration", details={"errors": errors})
    return result
