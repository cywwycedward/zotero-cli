"""Tests for zotero_cli.utils.audit_log."""
from __future__ import annotations

import json
from pathlib import Path

from zotero_cli.utils.audit_log import AuditEntry, write_entry

# ── Step 1: Basic JSONL append writer ──────────────────────────────────────


def test_writes_jsonl_line(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    entry = AuditEntry(
        timestamp="2026-06-08T12:00:00Z",
        profile="default",
        command="list-items",
        args={"format": "json", "limit": 10},
        result="success",
        affected_keys=[],
        elapsed_ms=42,
    )
    write_entry(log_path=log, entry=entry)

    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["timestamp"] == "2026-06-08T12:00:00Z"
    assert data["profile"] == "default"
    assert data["command"] == "list-items"
    assert data["args"] == {"format": "json", "limit": 10}
    assert data["result"] == "success"
    assert data["affected_keys"] == []
    assert data["elapsed_ms"] == 42


def test_appends_multiple_entries(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    for i in range(3):
        entry = AuditEntry(
            timestamp=f"2026-06-08T12:00:{i:02d}Z",
            profile="default",
            command="list-items",
            args={},
            result="success",
            affected_keys=[],
            elapsed_ms=i * 10,
        )
        write_entry(log_path=log, entry=entry)

    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_creates_parent_dir(tmp_path: Path) -> None:
    log = tmp_path / "sub" / "nested" / "audit.log"
    entry = AuditEntry(
        timestamp="2026-06-08T12:00:00Z",
        profile="default",
        command="list-items",
        args={},
        result="success",
        affected_keys=[],
        elapsed_ms=0,
    )
    write_entry(log_path=log, entry=entry)
    assert log.exists()


def test_failure_includes_error_fields(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    entry = AuditEntry(
        timestamp="2026-06-08T12:00:00Z",
        profile="default",
        command="list-items",
        args={},
        result="failure",
        affected_keys=[],
        elapsed_ms=10,
        error_code="E001",
        error_message="Something went wrong",
    )
    write_entry(log_path=log, entry=entry)

    lines = log.read_text(encoding="utf-8").strip().splitlines()
    data = json.loads(lines[0])
    assert data["result"] == "failure"
    assert data["error_code"] == "E001"
    assert data["error_message"] == "Something went wrong"
