"""Tests for zotero_cli.utils.audit_log."""
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import zotero_cli.utils.audit_log as audit_log_module
from zotero_cli.utils.audit_log import AuditEntry, _mask_args, write_entry

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


# ── Step 2: Sensitive-field masking ─────────────────────────────────────────


def test_api_key_field_masked() -> None:
    args = {"api_key": "abcd1234efgh5678", "collection": "ABC123"}
    masked = cast(dict[str, object], _mask_args(args))
    assert masked["api_key"] == "abcd****"
    assert masked["collection"] == "ABC123"


def test_password_redacted() -> None:
    args = {"password": "secret123"}
    masked = cast(dict[str, object], _mask_args(args))
    assert masked["password"] == "[REDACTED]"


def test_nested_password_redacted() -> None:
    args = {"webdav": {"password": "secret123"}}
    masked = cast(dict[str, object], _mask_args(args))
    assert cast(dict[str, object], masked["webdav"])["password"] == "[REDACTED]"


def test_short_api_key_fully_masked() -> None:
    args = {"api_key": "abc"}
    masked = cast(dict[str, object], _mask_args(args))
    assert masked["api_key"] == "****"


# ── Step 3: Gzip rotation ───────────────────────────────────────────────────


def test_no_rotation_below_threshold(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    log.write_text("x" * 100, encoding="utf-8")
    # Threshold is 10 MB, so 100 bytes is well below
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
    # No archive should have been created
    archives = list(tmp_path.glob("audit.log.*.gz"))
    assert archives == []


def test_rotates_at_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass 10 MB threshold: set rotate bytes to 100, fill log past it."""
    monkeypatch.setattr(audit_log_module, "AUDIT_LOG_ROTATE_BYTES", 100)
    log = tmp_path / "audit.log"
    # Fill with old content way past the threshold
    old_content = "x" * 150  # > 100
    log.write_text(old_content, encoding="utf-8")

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

    archives = sorted(tmp_path.glob("audit.log.*.gz"))
    assert len(archives) == 1
    # After rotation, log should only contain the new entry (1 line)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_archive_name_uses_entry_year_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_log_module, "AUDIT_LOG_ROTATE_BYTES", 100)
    log = tmp_path / "audit.log"
    log.write_text("x" * 150, encoding="utf-8")

    entry = AuditEntry(
        timestamp="2026-12-15T00:00:00Z",
        profile="default",
        command="list-items",
        args={},
        result="success",
        affected_keys=[],
        elapsed_ms=0,
    )
    write_entry(log_path=log, entry=entry)

    archives = list(tmp_path.glob("audit.log.*.gz"))
    assert len(archives) == 1
    assert archives[0].name == "audit.log.2026-12.gz"
