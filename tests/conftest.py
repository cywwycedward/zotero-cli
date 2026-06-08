"""Shared pytest fixtures for the whole project."""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_audit_log(tmp_path):
    """Fresh audit log path under pytest tmp_path; auto-cleaned."""
    return tmp_path / "audit.log"
