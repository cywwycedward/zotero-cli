"""Integration tests for items commands via CliRunner on full cli.app."""

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
    """Set up a minimal config for testing items commands."""
    cfg = tmp_path / "zotero-cli" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from zotero_cli.adapters.config_store import write_toml

    write_toml(
        cfg,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    return cfg


class TestItemsList:
    def test_default_kv_list_output(self, mocker, runner, tmp_profile) -> None:
        mock_api = mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[{"key": "ABC", "title": "Test Paper", "itemType": "journalArticle"}],
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.count_items",
            return_value=1,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.last_modified_version",
            return_value=10,
        )

        result = runner.invoke(app, ["items", "list"])
        assert result.exit_code == 0
        assert "key: ABC" in result.stdout
        assert "title: Test Paper" in result.stdout
        assert result.stderr == ""
        mock_api.assert_called_once()

    def test_json_envelope_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[{"key": "ABC"}],
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.count_items",
            return_value=1,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.last_modified_version",
            return_value=10,
        )

        result = runner.invoke(app, ["--json", "items", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert parsed["meta"]["command"] == "items.list"
        assert result.stderr == ""


class TestItemsShow:
    def test_not_found_default_mode(self, mocker, runner, tmp_profile) -> None:
        from zotero_cli.models.errors import ItemNotFoundError

        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            side_effect=ItemNotFoundError("Item 'NOPE' not found"),
        )

        result = runner.invoke(app, ["items", "show", "NOPE"])
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "ITEM_NOT_FOUND" in result.stderr

    def test_not_found_json_mode(self, mocker, runner, tmp_profile) -> None:
        from zotero_cli.models.errors import ItemNotFoundError

        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            side_effect=ItemNotFoundError("Item 'NOPE' not found"),
        )

        result = runner.invoke(app, ["--json", "items", "show", "NOPE"])
        assert result.exit_code == 1
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is False
        assert parsed["error"]["code"] == "ITEM_NOT_FOUND"
        assert result.stderr == ""


class TestItemsCreate:
    def test_create_default_output(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_items",
            return_value={
                "successful": [{"index": 0, "key": "NEWKEY", "version": 0}],
                "unchanged": [],
                "failed": [],
            },
        )

        result = runner.invoke(
            app, ["items", "create", "--type", "journalArticle", "--title", "Test"]
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout

    def test_create_json_mode(self, mocker, runner, tmp_profile, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_items",
            return_value={
                "successful": [{"index": 0, "key": "NEWKEY", "version": 0}],
                "unchanged": [],
                "failed": [],
            },
        )

        result = runner.invoke(
            app, ["--json", "items", "create", "--type", "journalArticle", "--title", "Test"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert parsed["meta"]["command"] == "items.create"


class TestItemsUpdate:
    def test_update_default_output(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            return_value={"key": "K1", "data": {"title": "Old"}, "version": 1},
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.update_item",
            return_value=True,
        )

        result = runner.invoke(app, ["items", "update", "K1", "--title", "New Title"])
        assert result.exit_code == 0
        assert "Updated" in result.stdout


class TestItemsDelete:
    def test_delete_default_output(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            return_value={"key": "K1", "version": 1},
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.delete_item",
            return_value=True,
        )

        result = runner.invoke(app, ["items", "delete", "K1"])
        assert result.exit_code == 0
        assert "Deleted" in result.stdout


class TestItemsExport:
    def test_export_bibtex_raw(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.export_items",
            return_value=b"@article{key, title={Test}}",
        )

        result = runner.invoke(app, ["items", "export", "--format", "bibtex"])
        assert result.exit_code == 0
        assert "@article{key, title={Test}}" in result.stdout

    def test_export_json_mode(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.export_items",
            return_value=b"@article{key, title={Test}}",
        )

        result = runner.invoke(app, ["--json", "items", "export", "--format", "bibtex"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert parsed["meta"]["command"] == "items.export"

    def test_export_quiet_rejected(self, mocker, runner, tmp_profile) -> None:
        result = runner.invoke(app, ["--quiet", "items", "export", "--format", "bibtex"])
        assert result.exit_code == 64
