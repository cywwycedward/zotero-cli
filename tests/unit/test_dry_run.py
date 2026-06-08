"""Tests for --dry-run behavior in items write commands."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from zotero_cli.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_profile(monkeypatch, tmp_path):
    cfg = tmp_path / "zotero-cli" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from zotero_cli.adapters.config_store import write_toml

    write_toml(
        cfg,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    return cfg


class TestDryRun:
    def test_create_dry_run_does_not_call_api(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_create = mocker.patch("zotero_cli.services.item_service.ItemService.create")
        result = runner.invoke(
            app,
            ["items", "create", "--type", "journalArticle", "--title", "Test", "--dry-run"],
        )
        assert result.exit_code == 0
        mock_create.assert_not_called()

    def test_create_dry_run_returns_preview(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            [
                "--json",
                "items",
                "create",
                "--type",
                "journalArticle",
                "--title",
                "Test",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        assert env["data"]["dry_run"] is True
        assert "would_create" in env["data"]

    def test_create_dry_run_with_attach(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        pdf = tmp_path / "test.pdf"
        pdf.write_text("dummy")
        result = runner.invoke(
            app,
            [
                "--json",
                "items",
                "create",
                "--type",
                "journalArticle",
                "--title",
                "Test",
                "--attach",
                str(pdf),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["data"]["dry_run"] is True
        assert "would_upload" in env["data"]

    def test_update_dry_run_does_not_call_api(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_update = mocker.patch("zotero_cli.services.item_service.ItemService.update")
        result = runner.invoke(
            app,
            ["items", "update", "ABC123", "--title", "New Title", "--dry-run"],
        )
        assert result.exit_code == 0
        mock_update.assert_not_called()

    def test_update_dry_run_returns_preview(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            ["--json", "items", "update", "ABC123", "--title", "New Title", "--dry-run"],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["data"]["dry_run"] is True
        assert env["data"]["would_update"]["key"] == "ABC123"

    def test_delete_dry_run_does_not_call_api(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_delete = mocker.patch("zotero_cli.services.item_service.ItemService.delete")
        result = runner.invoke(
            app,
            ["items", "delete", "ABC123", "--dry-run"],
        )
        assert result.exit_code == 0
        mock_delete.assert_not_called()

    def test_delete_dry_run_returns_preview(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(
            app,
            ["--json", "items", "delete", "ABC123", "DEF456", "--dry-run"],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["data"]["dry_run"] is True
        assert env["data"]["would_delete"] == ["ABC123", "DEF456"]

    def test_attach_dry_run_does_not_upload(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mock_attach = mocker.patch(
            "zotero_cli.services.attachment_service.AttachmentService.attach"
        )
        pdf = tmp_path / "test.pdf"
        pdf.write_text("dummy")
        result = runner.invoke(
            app,
            ["items", "attach", "PARENT1", str(pdf), "--dry-run"],
        )
        assert result.exit_code == 0
        mock_attach.assert_not_called()

    def test_attach_dry_run_returns_preview(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        pdf = tmp_path / "test.pdf"
        pdf.write_text("dummy")
        result = runner.invoke(
            app,
            ["--json", "items", "attach", "PARENT1", str(pdf), "--dry-run"],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["data"]["dry_run"] is True
        assert len(env["data"]["would_upload"]) == 1
