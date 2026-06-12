"""Tests for --version / -v global option."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from zotero_cli import __version__
from zotero_cli.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestVersionOption:
    def test_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert result.stdout.strip() == f"zotero-cli {__version__}"

    def test_version_short_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert result.stdout.strip() == f"zotero-cli {__version__}"
