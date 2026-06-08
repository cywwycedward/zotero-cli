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
