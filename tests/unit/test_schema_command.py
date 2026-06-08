"""Tests for commands/schema.py — schema introspection command."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from zotero_cli.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestSchemaCommand:
    def test_schema_full_tree(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema"])
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        tree = env["data"]
        assert tree["name"] == "zotero-cli"
        group_names = [g["name"] for g in tree["groups"]]
        assert "items" in group_names
        assert "feeds" in group_names
        assert "config" in group_names
        assert "collections" in group_names
        assert "tags" in group_names

    def test_schema_full_tree_has_params(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema"])
        env = json.loads(result.stdout)
        items_group = next(g for g in env["data"]["groups"] if g["name"] == "items")
        list_cmd = next(c for c in items_group["commands"] if c["name"] == "list")
        assert "params" in list_cmd
        param_names = [p["name"] for p in list_cmd["params"]]
        assert "limit" in param_names

    def test_schema_group_by_name(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema", "--command", "items"])
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        data = env["data"]
        assert data["name"] == "items"
        cmd_names = [c["name"] for c in data["commands"]]
        assert "list" in cmd_names
        assert "create" in cmd_names

    def test_schema_dotted_command(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema", "--command", "items.list"])
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        data = env["data"]
        assert data["name"] == "items.list"
        assert "params" in data
        param_names = [p["name"] for p in data["params"]]
        assert "limit" in param_names
        assert "collection" in param_names

    def test_schema_dotted_command_with_params_detail(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema", "--command", "items.list"])
        env = json.loads(result.stdout)
        params = env["data"]["params"]
        limit_param = next(p for p in params if p["name"] == "limit")
        assert limit_param["type"] == "integer"
        assert limit_param["kind"] == "option"

    def test_schema_unknown_group_returns_error(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema", "--command", "nonexistent"])
        assert result.exit_code != 0
        env = json.loads(result.stdout)
        assert env["ok"] is False
        assert "not found" in env["error"]["message"].lower()

    def test_schema_unknown_subcommand_returns_error(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema", "--command", "items.nonexistent"])
        assert result.exit_code != 0
        env = json.loads(result.stdout)
        assert env["ok"] is False
        assert "not found" in env["error"]["message"].lower()

    def test_schema_always_json_even_without_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema"])
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert "ok" in env
        assert "data" in env
        assert "meta" in env

    def test_schema_quiet_rejected_as_json(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--quiet", "schema"])
        env = json.loads(result.stdout)
        assert env["ok"] is False
        assert "MUTUALLY_EXCLUSIVE_ARGS" in env["error"]["code"]

    def test_schema_positional_argument_kind(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["schema", "--command", "items.show"])
        env = json.loads(result.stdout)
        params = env["data"]["params"]
        key_param = next(p for p in params if p["name"] == "key")
        assert key_param["kind"] == "argument"
        assert "opts" not in key_param
