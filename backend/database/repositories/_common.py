from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any

from ..utils import loads


def row_to_dict(
    row: sqlite3.Row | None,
    *,
    json_fields: Mapping[str, str] | None = None,
    bool_fields: Iterable[str] = (),
) -> dict[str, Any] | None:
    if row is None:
        return None
    record = dict(row)
    for column, key in (json_fields or {}).items():
        record[key] = loads(record.pop(column, None), [] if key.endswith("ids") else {})
    for field in bool_fields:
        if field in record:
            record[field] = bool(record[field])
    return record


def rows_to_dicts(
    rows: Iterable[sqlite3.Row],
    *,
    json_fields: Mapping[str, str] | None = None,
    bool_fields: Iterable[str] = (),
) -> list[dict[str, Any]]:
    return [
        row_to_dict(row, json_fields=json_fields, bool_fields=bool_fields)
        for row in rows
    ]
