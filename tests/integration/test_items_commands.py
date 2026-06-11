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
            return_value=[
                {
                    "key": "ABC",
                    "version": 1,
                    "data": {
                        "key": "ABC",
                        "title": "Test Paper",
                        "itemType": "journalArticle",
                        "creators": [],
                        "date": "2026",
                        "tags": [],
                    },
                }
            ],
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
        assert "itemType: journalArticle" in result.stdout
        assert result.stderr == ""
        mock_api.assert_called_once()

    def test_json_envelope_output(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[
                {
                    "key": "ABC",
                    "version": 1,
                    "data": {"key": "ABC", "title": "Test", "itemType": "journalArticle"},
                }
            ],
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

    def test_quiet_outputs_keys(self, mocker, runner, tmp_profile) -> None:
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.items_top",
            return_value=[
                {"key": "A1", "data": {"key": "A1", "title": "P1"}},
                {"key": "B2", "data": {"key": "B2", "title": "P2"}},
            ],
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.count_items",
            return_value=2,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.last_modified_version",
            return_value=10,
        )

        result = runner.invoke(app, ["--quiet", "items", "list"])
        assert result.exit_code == 0
        lines = result.stdout.strip().split("\n")
        assert lines == ["A1", "B2"]


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

    def test_create_with_attach_shows_both_keys(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        """items create --attach should output both parent and attachment keys."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        pdf = tmp_profile.parent / "test.pdf"
        pdf.write_text("dummy pdf")
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_items",
            return_value={
                "successful": [{"index": 0, "key": "PARENT1", "version": 0}],
                "unchanged": [],
                "failed": [],
            },
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.attachment_both",
            return_value={
                "success": ["ATT1"],
                "unchanged": [],
                "failure": [],
            },
        )

        result = runner.invoke(
            app,
            [
                "items",
                "create",
                "--type",
                "journalArticle",
                "--title",
                "Test",
                "--attach",
                str(pdf),
                "--attach-title",
                "Custom Title",
            ],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "PARENT1" in result.stdout
        assert "ATT1" in result.stdout


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

    def test_update_with_attach_includes_parent_key_in_affected(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        """update --attach affected_keys must include parent item key + attachment key."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        pdf = tmp_profile.parent / "test.pdf"
        pdf.write_text("dummy pdf")
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            return_value={"key": "K1", "data": {"title": "Old"}, "version": 1},
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.update_item",
            return_value=True,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.attachment_simple",
            return_value={
                "success": ["ATT1"],
                "unchanged": [],
                "failure": [],
            },
        )
        result = runner.invoke(
            app,
            ["--json", "items", "update", "K1", "--title", "New", "--attach", str(pdf)],
        )
        assert result.exit_code == 0
        import json

        env = json.loads(result.stdout)
        assert env["ok"] is True
        assert "uploaded" in env["data"]
        assert "K1" in env["meta"]["affected_keys"]
        assert "ATT1" in env["meta"]["affected_keys"]


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

    def test_json_output_writes_file_and_envelope(
        self, mocker, runner, tmp_profile, tmp_path
    ) -> None:
        """--json --output must write the file AND return JSON envelope."""
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.export_items",
            return_value=b"@article{a, title={Test}}",
        )
        out_file = tmp_path / "out.bib"
        result = runner.invoke(
            app,
            ["--json", "items", "export", "--format", "bibtex", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        assert out_file.read_bytes() == b"@article{a, title={Test}}"
        envelope = json.loads(result.stdout)
        assert envelope["ok"] is True
        assert envelope["data"]["format"] == "bibtex"
        assert envelope["data"]["byte_size"] == len(b"@article{a, title={Test}}")
        assert "output_path" in envelope["data"]
        assert "content" not in envelope["data"]

    def test_plain_output_writes_file(self, mocker, runner, tmp_profile, tmp_path) -> None:
        """--output without --json must write file."""
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.export_items",
            return_value=b"@article{a, title={Test}}",
        )
        out_file = tmp_path / "out.bib"
        result = runner.invoke(
            app,
            ["items", "export", "--format", "bibtex", "--output", str(out_file)],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        assert out_file.read_bytes() == b"@article{a, title={Test}}"
        assert "Exported" in result.stderr


class TestItemsAttach:
    def test_attach_command_exists(self, runner, tmp_profile) -> None:
        """Verify items attach subcommand is registered and shows help."""
        result = runner.invoke(app, ["items", "attach", "--help"])
        assert result.exit_code == 0
        assert "attach" in result.stdout.lower() or "Usage" in result.stdout

    def test_attach_default_output(
        self,
        mocker,
        runner,
        tmp_profile,
        monkeypatch,
        tmp_path,
    ) -> None:
        """items attach should show 'Attached' in summary output."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        pdf = tmp_profile.parent / "test.pdf"
        pdf.write_text("dummy pdf")
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.attachment_simple",
            return_value={
                "success": ["ATT1"],
                "unchanged": [],
                "failure": [],
            },
        )

        result = runner.invoke(app, ["items", "attach", "PARENT", str(pdf)])
        assert result.exit_code == 0
        assert "Attached" in result.stdout
        assert "ATT1" in result.stdout

    def test_attach_with_force_zfs_rejected(self, mocker, runner, tmp_profile) -> None:
        """ZFS --force should be rejected."""
        pdf = tmp_profile.parent / "test.pdf"
        pdf.write_text("dummy pdf")

        result = runner.invoke(app, ["items", "attach", "PARENT", str(pdf), "--force"])
        assert result.exit_code == 64 or "force" in result.stderr.lower()

    def test_attach_reuse_key_not_found(
        self,
        mocker,
        runner,
        tmp_profile,
        monkeypatch,
        tmp_path,
    ) -> None:
        """--reuse-key with non-existent key returns ITEM_NOT_FOUND.
        The ZFS guard was removed after pyzotero 1.13.1 fixed issue #322."""
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        pdf = tmp_profile.parent / "test.pdf"
        pdf.write_text("dummy pdf")

        from zotero_cli.models.errors import ItemNotFoundError

        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item",
            side_effect=ItemNotFoundError("Item 'NOPE' not found"),
        )

        result = runner.invoke(app, ["items", "attach", "PARENT", str(pdf), "--reuse-key", "NOPE"])
        assert result.exit_code == 1
        assert "ITEM_NOT_FOUND" in result.stderr


class TestGroupWebdavRejection:
    """Verify group library + WebDAV is rejected (design §10.0.1)."""

    def test_config_validate_rejects(self, runner, monkeypatch, tmp_path) -> None:
        config_dir = tmp_path / "zotero-cli"
        config_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from zotero_cli.adapters.config_store import write_toml

        write_toml(
            config_dir / "config.toml",
            {
                "default": {
                    "api_key": "k",
                    "library_id": "1",
                    "library_type": "group",
                    "webdav": {"url": "https://x", "username": "u", "password": "p"},
                }
            },
        )
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 1
        assert "UNSUPPORTED_LIBRARY_TYPE" in result.stderr
