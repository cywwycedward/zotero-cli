"""tests/integration/test_items_find_doi_command.py — CLI tests for items find-doi."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from zotero_cli.cli import app

TARGET = "10.1038/s41586-020-2649-2"


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


def _item(key: str, doi: str) -> dict[str, object]:
    return {
        "key": key,
        "version": 1,
        "data": {
            "key": key,
            "title": f"Paper {key}",
            "itemType": "journalArticle",
            "creators": [],
            "date": "2020",
            "tags": [],
            "DOI": doi,
        },
    }


class TestFindDoiOutput:
    def test_default_kv_list_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[_item("MATCH", TARGET)],
        )
        result = runner.invoke(app, ["items", "find-doi", TARGET])
        assert result.exit_code == 0
        assert "key: MATCH" in result.stdout
        assert "title: Paper MATCH" in result.stdout
        assert result.stderr == ""

    def test_not_found_empty_exit_zero(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[],
        )
        result = runner.invoke(app, ["items", "find-doi", TARGET])
        assert result.exit_code == 0
        assert result.stdout.strip() == ""

    def test_quiet_outputs_keys(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[_item("M1", TARGET), _item("M2", TARGET)],
        )
        result = runner.invoke(app, ["--quiet", "items", "find-doi", TARGET])
        assert result.exit_code == 0
        assert result.stdout.strip().split("\n") == ["M1", "M2"]

    def test_quiet_not_found_no_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[],
        )
        result = runner.invoke(app, ["--quiet", "items", "find-doi", TARGET])
        assert result.exit_code == 0
        assert result.stdout == ""

    def test_json_envelope(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[_item("MATCH", TARGET)],
        )
        result = runner.invoke(
            app, ["--json", "items", "find-doi", f"https://doi.org/{TARGET}"]
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        assert env["meta"]["command"] == "items.find_doi"
        assert env["meta"]["normalized_doi"] == TARGET
        assert env["meta"]["query_doi"] == f"https://doi.org/{TARGET}"
        assert env["meta"]["count"] == 1
        assert env["meta"]["collection"] is None
        assert len(env["data"]) == 1
        assert env["data"][0]["key"] == "MATCH"

    def test_json_collection_scope(self, mocker, runner, tmp_profile) -> None:
        mock = mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[],
        )
        result = runner.invoke(
            app, ["--json", "items", "find-doi", TARGET, "--collection", "C1"]
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["meta"]["collection"] == "C1"
        assert mock.call_args.kwargs["collection"] == "C1"

    def test_default_filters_fields_but_all_fields_exposes_doi(
        self, mocker, runner, tmp_profile
    ) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[_item("MATCH", TARGET)],
        )
        # Default obeys item_fields.list (no DOI in the default field set).
        default = runner.invoke(app, ["items", "find-doi", TARGET])
        assert default.exit_code == 0
        assert "key: MATCH" in default.stdout
        assert "DOI:" not in default.stdout
        # --all-fields disables the filter and exposes the DOI field.
        full = runner.invoke(app, ["items", "find-doi", TARGET, "--all-fields"])
        assert full.exit_code == 0
        assert f"DOI: {TARGET}" in full.stdout


class TestFindDoiErrors:
    def test_invalid_doi(self, runner, tmp_profile) -> None:
        result = runner.invoke(app, ["--json", "items", "find-doi", "not-a-doi"])
        assert result.exit_code == 1
        env = json.loads(result.stdout)
        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_FIELD"

    def test_help_registered(self, runner, tmp_profile) -> None:
        result = runner.invoke(app, ["items", "find-doi", "--help"])
        assert result.exit_code == 0
        assert "find-doi" in result.stdout or "Usage" in result.stdout
