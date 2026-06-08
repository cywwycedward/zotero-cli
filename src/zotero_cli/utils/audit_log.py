"""Audit log: append-only JSONL with sensitive-field masking and gzip rotation.

Design: §9 Audit Log (doc/design.md)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    """A single audit-log entry describing one CLI action."""

    timestamp: str
    profile: str
    command: str
    args: dict[str, Any]
    result: str
    affected_keys: list[str]
    elapsed_ms: int
    error_code: str | None = None
    error_message: str | None = None


def write_entry(*, log_path: Path, entry: AuditEntry) -> None:
    """Append *entry* as a JSONL line to *log_path*.

    1. Create parent directory if needed.
    2. Mask sensitive fields in ``args`` (api_key, password, …).
    3. Omit ``None`` values (except ``args`` and ``affected_keys`` which always appear).
    4. Write one JSON line (append, UTF-8).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(entry)
    data["args"] = _mask_args(data["args"])

    # Drop None values, but keep args and affected_keys even if empty
    filtered = {}
    for key, value in data.items():
        if value is not None or key in ("args", "affected_keys"):
            filtered[key] = value

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(filtered, ensure_ascii=False, sort_keys=True) + "\n")


def _mask_args(obj: object) -> object:
    """Recursively mask / redact sensitive values inside *obj*.

    Currently a pass-through; full masking logic added in Step 2.
    """
    return obj


def _maybe_rotate(log_path: Path, entry_timestamp: str) -> None:
    """Archives and truncates *log_path* if it exceeds the rotation threshold.

    Currently a no-op; rotation logic added in Step 3.
    """
