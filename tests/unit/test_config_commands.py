from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zotero_cli.adapters.config_store import read_toml, write_toml
from zotero_cli.cli import app

runner = CliRunner()


@pytest.fixture
def cfg_at(monkeypatch, tmp_path):
    """Redirect config path to tmp_path by setting XDG_CONFIG_HOME."""
    config_dir = tmp_path / "zotero-cli"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return config_dir / "config.toml"


# ── init ───────────────────────────────────────────────────────────────────


def test_init_creates_file_with_0600(cfg_at: Path) -> None:
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert cfg_at.exists()
    mode = cfg_at.stat().st_mode & 0o777
    assert oct(mode) == "0o600"


def test_init_refuses_overwrite_without_force(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 4  # ConfigInvalidError → local_error
    assert result.stdout == ""
    assert "exists" in result.stderr.lower() or "already" in result.stderr.lower()


def test_init_force_overwrites(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "init", "--force"])
    assert result.exit_code == 0


def test_init_respects_profile_flag(cfg_at: Path) -> None:
    """config init --profile work should create a 'work' profile, not 'default'."""
    result = runner.invoke(app, ["--profile", "work", "config", "init"])
    assert result.exit_code == 0
    data = read_toml(cfg_at)
    assert "work" in data
    assert "default" not in data


# ── show ───────────────────────────────────────────────────────────────────


def test_show_yaml_default_with_masked_secrets(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "secretkey1234", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "secr****" in result.stdout
    assert "secretkey1234" not in result.stdout
    assert result.stderr == ""


def test_show_json_emits_full_envelope(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["--json", "config", "show"])
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is True
    assert parsed["data"]["library_id"] == "1"
    assert result.stderr == ""


def test_show_unknown_profile_writes_stderr(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["--profile", "missing", "config", "show"])
    assert result.exit_code == 1  # InvalidProfileError → user_error
    assert result.stdout == ""
    assert "INVALID_PROFILE" in result.stderr


def test_show_unknown_profile_json_writes_stdout(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["--json", "--profile", "missing", "config", "show"])
    assert result.exit_code == 1
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "INVALID_PROFILE"
    assert result.stderr == ""


# ── set ────────────────────────────────────────────────────────────────────


def test_set_top_level_writes_back(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "old", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "set", "api_key", "new"])
    assert result.exit_code == 0
    assert read_toml(cfg_at)["default"]["api_key"] == "new"
    mode = cfg_at.stat().st_mode & 0o777
    assert oct(mode) == "0o600"


def test_set_nested_webdav_password(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {
                "api_key": "k",
                "library_id": "1",
                "library_type": "user",
                "webdav": {"url": "https://x", "username": "u", "password": "old"},
            }
        },
    )
    runner.invoke(app, ["config", "set", "webdav.password", "new"])
    assert read_toml(cfg_at)["default"]["webdav"]["password"] == "new"


def test_set_breaks_compat_matrix_rejected(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {
                "api_key": "k",
                "library_id": "1",
                "library_type": "user",
                "webdav": {"url": "https://x", "username": "u", "password": "p"},
            }
        },
    )
    result = runner.invoke(app, ["config", "set", "library_type", "group"])
    assert result.exit_code == 1  # UnsupportedLibraryTypeError → user_error
    assert result.stdout == ""
    assert "UNSUPPORTED_LIBRARY_TYPE" in result.stderr


def test_set_list_field_from_csv(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    runner.invoke(app, ["config", "set", "item_fields.list", "key,title,date"])
    assert read_toml(cfg_at)["default"]["item_fields"]["list"] == ["key", "title", "date"]


def test_set_coerces_int(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {
                "api_key": "k",
                "library_id": "1",
                "library_type": "user",
                "webdav": {"url": "https://x", "username": "u", "password": "p"},
            }
        },
    )
    runner.invoke(app, ["config", "set", "webdav.timeout", "30"])
    assert read_toml(cfg_at)["default"]["webdav"]["timeout"] == 30


def test_set_coerces_bool_true(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {
                "api_key": "k",
                "library_id": "1",
                "library_type": "user",
                "webdav": {"url": "https://x", "username": "u", "password": "p"},
            }
        },
    )
    runner.invoke(app, ["config", "set", "webdav.verify_ssl", "false"])
    assert read_toml(cfg_at)["default"]["webdav"]["verify_ssl"] is False


def test_set_coerces_float(cfg_at: Path) -> None:
    """Float coerced value for int field fails pydantic validation."""
    write_toml(
        cfg_at,
        {
            "default": {
                "api_key": "k",
                "library_id": "1",
                "library_type": "user",
                "webdav": {"url": "https://x", "username": "u", "password": "p"},
            }
        },
    )
    result = runner.invoke(app, ["config", "set", "webdav.timeout", "1.5"])
    # pydantic rejects 1.5 for int-typed timeout field
    assert result.exit_code != 0


def test_set_preserves_string(cfg_at: Path) -> None:
    """Non-numeric, non-bool values stay as strings."""
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    runner.invoke(app, ["config", "set", "api_key", "abc123def456"])
    assert read_toml(cfg_at)["default"]["api_key"] == "abc123def456"


# ── get ────────────────────────────────────────────────────────────────────


def test_get_returns_value(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "12345", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "get", "library_id"])
    assert result.exit_code == 0
    assert "value: 12345" in result.stdout


def test_get_password_masked(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {
                "api_key": "k",
                "library_id": "1",
                "library_type": "user",
                "webdav": {"url": "https://x", "username": "u", "password": "secret"},
            }
        },
    )
    result = runner.invoke(app, ["config", "get", "webdav.password"])
    assert "secret" not in result.stdout
    assert "****" in result.stdout


def test_get_unknown_key_invalid_field(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "get", "nonexistent"])
    assert result.exit_code == 1  # InvalidFieldError → user_error
    assert result.stdout == ""
    assert "INVALID_FIELD" in result.stderr


# ── validate ───────────────────────────────────────────────────────────────


def test_validate_passes(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 0
    assert "valid" in result.stdout.lower()


def test_validate_group_with_webdav_fails(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
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
    assert result.exit_code == 1  # UnsupportedLibraryTypeError → user_error
    assert result.stdout == ""
    assert "UNSUPPORTED_LIBRARY_TYPE" in result.stderr


# ── profiles ───────────────────────────────────────────────────────────────


def test_profiles_lists_all(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {"api_key": "k", "library_id": "1", "library_type": "user"},
            "work": {"api_key": "k", "library_id": "2", "library_type": "user"},
        },
    )
    result = runner.invoke(app, ["config", "profiles"])
    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "work" in result.stdout


def test_profiles_quiet_outputs_names(cfg_at: Path) -> None:
    write_toml(
        cfg_at,
        {
            "default": {"api_key": "k", "library_id": "1", "library_type": "user"},
            "work": {"api_key": "k", "library_id": "2", "library_type": "user"},
        },
    )
    result = runner.invoke(app, ["--quiet", "config", "profiles"])
    assert sorted(result.stdout.strip().split("\n")) == ["default", "work"]
