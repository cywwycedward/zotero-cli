"""Integration tests for collections commands via CliRunner on full cli.app."""

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
    """Set up a minimal config for testing collections commands."""
    cfg = tmp_path / "zotero-cli" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from zotero_cli.adapters.config_store import write_toml

    write_toml(
        cfg,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    return cfg


class TestCollectionsList:
    def test_default_tree_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.collections",
            return_value=[
                {"key": "R", "data": {"name": "Root"}, "meta": {"numItems": 10}},
            ],
        )

        result = runner.invoke(app, ["collections", "list"])
        assert result.exit_code == 0
        assert "Root" in result.stdout
        assert result.stderr == ""

    def test_json_envelope_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.collections",
            return_value=[
                {"key": "R", "data": {"name": "Root"}, "meta": {"numItems": 10}},
            ],
        )

        result = runner.invoke(app, ["--json", "collections", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert parsed["meta"]["command"] == "collections.list"
        assert result.stderr == ""


class TestCollectionsShow:
    def test_show_found(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.collections",
            return_value=[
                {"key": "R", "data": {"name": "Root"}, "meta": {"numItems": 10}},
            ],
        )

        result = runner.invoke(app, ["collections", "show", "R"])
        assert result.exit_code == 0
        assert result.stderr == ""

    def test_not_found(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.collections",
            return_value=[],
        )

        result = runner.invoke(app, ["collections", "show", "NOPE"])
        assert result.exit_code == 1
        assert "COLLECTION_NOT_FOUND" in result.stderr


class TestCollectionsCreate:
    def test_create_success(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_collection",
            return_value={"key": "NEW"},
        )

        result = runner.invoke(app, ["collections", "create", "--name", "Test"])
        assert result.exit_code == 0
        assert "Created" in result.stdout

    def test_create_json_mode(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_collection",
            return_value={"key": "NEW"},
        )

        result = runner.invoke(app, ["--json", "collections", "create", "--name", "Test"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert result.stderr == ""


class TestCollectionsDelete:
    def test_delete_success(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.delete_collection",
            return_value=True,
        )

        result = runner.invoke(app, ["collections", "delete", "DEL"])
        assert result.exit_code == 0
        assert "Deleted" in result.stdout


class TestCollectionsAddItems:
    def test_add_items_success(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.add_to_collection",
            return_value=True,
        )

        result = runner.invoke(app, ["collections", "add-items", "COLL1", "ITEM1"])
        assert result.exit_code == 0
        assert "Added items to" in result.stdout


class TestCollectionsRemoveItems:
    def test_remove_items_success(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.remove_from_collection",
            return_value=True,
        )

        result = runner.invoke(app, ["collections", "remove-items", "COLL1", "ITEM1"])
        assert result.exit_code == 0
        assert "Removed items from" in result.stdout
