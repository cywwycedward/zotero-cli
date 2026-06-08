"""Verify --json + --quiet mutex is enforced before any service call."""
import json

import pytest
from typer.testing import CliRunner

from zotero_cli.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cfg_at(monkeypatch, tmp_path):
    config_dir = tmp_path / "zotero-cli"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from zotero_cli.adapters.config_store import write_toml
    write_toml(
        config_dir / "config.toml",
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    return config_dir / "config.toml"


def test_items_list_mutex_rejected_json_envelope_to_stdout(mocker, runner, cfg_at) -> None:
    spy = mocker.patch("zotero_cli.adapters.zotero_api.ZoteroAPI.items_top")
    result = runner.invoke(app, ["--json", "--quiet", "items", "list"])
    assert result.exit_code == 64
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"
    spy.assert_not_called()


def test_collections_list_mutex_rejected(mocker, runner, cfg_at) -> None:
    spy = mocker.patch("zotero_cli.adapters.zotero_api.ZoteroAPI.collections")
    result = runner.invoke(app, ["--json", "--quiet", "collections", "list"])
    assert result.exit_code == 64
    spy.assert_not_called()


def test_tags_list_mutex_rejected(mocker, runner, cfg_at) -> None:
    spy = mocker.patch("zotero_cli.adapters.zotero_api.ZoteroAPI.tags")
    result = runner.invoke(app, ["--json", "--quiet", "tags", "list"])
    assert result.exit_code == 64
    spy.assert_not_called()
