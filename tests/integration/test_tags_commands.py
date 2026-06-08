"""Integration tests for tags commands via CliRunner on full cli.app."""

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
    """Set up a minimal config for testing tags commands."""
    cfg = tmp_path / "zotero-cli" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from zotero_cli.adapters.config_store import write_toml

    write_toml(
        cfg,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    return cfg


class TestTagsList:
    def test_default_kv_list_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.tags",
            return_value=[{"tag": "nlp", "num_items": 5}],
        )

        result = runner.invoke(app, ["tags", "list"])
        assert result.exit_code == 0
        assert "nlp" in result.stdout
        assert result.stderr == ""

    def test_json_envelope_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.tags",
            return_value=[{"tag": "nlp", "num_items": 5}],
        )

        result = runner.invoke(app, ["--json", "tags", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert parsed["meta"]["command"] == "tags.list"
        assert result.stderr == ""


class TestTagsAdd:
    def test_adds_tag_to_item(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            return_value={"key": "I1", "data": {"tags": []}},
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.update_item",
            return_value=True,
        )

        result = runner.invoke(app, ["tags", "add", "nlp", "I1"])
        assert result.exit_code == 0
        assert "Tagged" in result.stdout


class TestTagsRemove:
    def test_removes_tag_from_item(
        self, mocker, runner, tmp_profile, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            return_value={"key": "I1", "data": {"tags": [{"tag": "nlp"}]}},
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.update_item",
            return_value=True,
        )

        result = runner.invoke(app, ["tags", "remove", "nlp", "I1"])
        assert result.exit_code == 0
        assert "Untagged" in result.stdout


class TestTagsRename:
    def test_renames_tag(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items",
            return_value=[
                {"key": "I1", "data": {"tags": [{"tag": "old"}, {"tag": "x"}]}},
            ],
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.update_item",
            return_value=True,
        )

        result = runner.invoke(app, ["tags", "rename", "old", "new"])
        assert result.exit_code == 0
        assert "Renamed" in result.stdout


class TestTagsDelete:
    def test_deletes_tag(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items",
            return_value=[{"key": "I1", "data": {"tags": [{"tag": "nlp"}]}}],
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.delete_tags",
            return_value=True,
        )

        result = runner.invoke(app, ["tags", "delete", "nlp"])
        assert result.exit_code == 0
        assert "Deleted" in result.stdout

    def test_json_envelope_output(self, mocker, runner, tmp_profile, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items",
            return_value=[{"key": "I1", "data": {"tags": [{"tag": "nlp"}]}}],
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.delete_tags",
            return_value=True,
        )

        result = runner.invoke(app, ["--json", "tags", "delete", "nlp"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["ok"] is True
        assert parsed["meta"]["command"] == "tags.delete"
        assert result.stderr == ""
