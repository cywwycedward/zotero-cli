from __future__ import annotations

import stat
from pathlib import Path

import pytest

from zotero_cli.adapters.config_store import (
    default_config_path,
    detect_sqlite_db,
    read_toml,
    write_toml,
)
from zotero_cli.models.errors import ConfigInvalidError, ConfigNotFoundError


class TestReadToml:
    def test_missing_raises_config_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigNotFoundError):
            read_toml(tmp_path / "nope.toml")

    def test_invalid_syntax_raises_config_invalid(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.toml"
        p.write_text("not = valid = toml")
        with pytest.raises(ConfigInvalidError):
            read_toml(p)

    def test_reads_valid_toml(self, tmp_path: Path) -> None:
        p = tmp_path / "c.toml"
        p.write_text('[default]\napi_key = "k"\nlibrary_id = "1"\nlibrary_type = "user"\n')
        result = read_toml(p)
        assert result == {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}}


class TestWriteToml:
    def test_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "c.toml"
        data = {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}}
        write_toml(p, data)
        assert read_toml(p) == data

    def test_sets_0600(self, tmp_path: Path) -> None:
        p = tmp_path / "c.toml"
        write_toml(p, {"x": {"y": 1}})
        mode = stat.S_IMODE(p.stat().st_mode)
        assert mode == 0o600

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        p = tmp_path / "subdir" / "c.toml"
        write_toml(p, {"x": {"y": 1}})
        assert p.exists()


class TestDefaultConfigPath:
    def test_ends_with_zotero_cli_config_toml(self) -> None:
        p = default_config_path()
        assert p.name == "config.toml"
        assert p.parent.name == "zotero-cli"


class TestDetectSqliteDb:
    def test_env_override_used(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "zotero.sqlite").touch()
        monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
        assert detect_sqlite_db() == str(tmp_path / "zotero.sqlite")

    def test_explicit_arg_wins(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "zotero.sqlite").touch()
        other = tmp_path / "other"
        other.mkdir()
        (other / "zotero.sqlite").touch()
        monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
        assert detect_sqlite_db(env_override=str(other)) == str(other / "zotero.sqlite")

    def test_none_when_missing(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert detect_sqlite_db() is None
