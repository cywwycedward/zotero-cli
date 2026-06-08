from __future__ import annotations

import pytest

from zotero_cli.adapters.config_store import write_toml
from zotero_cli.models.errors import (
    ConfigNotFoundError,
    InvalidProfileError,
    UnsupportedLibraryTypeError,
)
from zotero_cli.services.config_service import load_config, validate_profile

# ── load_config ────────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_missing_file_raises_config_not_found(self, tmp_path) -> None:
        with pytest.raises(ConfigNotFoundError):
            load_config(profile="default", config_path=tmp_path / "nope.toml")

    def test_unknown_profile_raises_invalid_profile(self, tmp_path) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
        )
        with pytest.raises(InvalidProfileError) as ei:
            load_config(profile="missing", config_path=tmp_path / "c.toml")
        assert "available" in (ei.value.hint or "").lower()

    def test_loads_valid_profile(self, tmp_path) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
        )
        cfg = load_config(profile="default", config_path=tmp_path / "c.toml")
        assert cfg.api_key == "k"
        assert cfg.library_id == "1"
        assert cfg.library_type == "user"


# ── env overrides ──────────────────────────────────────────────────────────


class TestEnvOverrides:
    def test_top_level_override(self, tmp_path, monkeypatch) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "from_file", "library_id": "1", "library_type": "user"}},
        )
        monkeypatch.setenv("ZOTERO_CLI_DEFAULT_API_KEY", "from_env")
        cfg = load_config(profile="default", config_path=tmp_path / "c.toml")
        assert cfg.api_key == "from_env"

    def test_webdav_password_override(self, tmp_path, monkeypatch) -> None:
        write_toml(
            tmp_path / "c.toml",
            {
                "work": {
                    "api_key": "k",
                    "library_id": "1",
                    "library_type": "user",
                    "webdav": {
                        "url": "https://x",
                        "username": "u",
                        "password": "from_file",
                    },
                }
            },
        )
        monkeypatch.setenv("ZOTERO_CLI_WORK_WEBDAV_PASSWORD", "from_env")
        cfg = load_config(profile="work", config_path=tmp_path / "c.toml")
        assert cfg.webdav is not None
        assert cfg.webdav.password == "from_env"

    def test_webdav_section_created_via_env(self, tmp_path, monkeypatch) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
        )
        monkeypatch.setenv("ZOTERO_CLI_DEFAULT_WEBDAV_URL", "https://x")
        monkeypatch.setenv("ZOTERO_CLI_DEFAULT_WEBDAV_USERNAME", "u")
        monkeypatch.setenv("ZOTERO_CLI_DEFAULT_WEBDAV_PASSWORD", "p")
        cfg = load_config(profile="default", config_path=tmp_path / "c.toml")
        assert cfg.webdav is not None
        assert cfg.webdav.url == "https://x"

    def test_list_field_override(self, tmp_path, monkeypatch) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
        )
        monkeypatch.setenv("ZOTERO_CLI_DEFAULT_ITEM_FIELDS_LIST", "key,title,date")
        cfg = load_config(profile="default", config_path=tmp_path / "c.toml")
        assert cfg.item_fields.list == ["key", "title", "date"]

    def test_other_profile_env_ignored(self, tmp_path, monkeypatch) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "from_file", "library_id": "1", "library_type": "user"}},
        )
        monkeypatch.setenv("ZOTERO_CLI_WORK_API_KEY", "should_not_apply")
        cfg = load_config(profile="default", config_path=tmp_path / "c.toml")
        assert cfg.api_key == "from_file"


# ── validate_profile ───────────────────────────────────────────────────────


class TestValidateProfile:
    def test_passes_silently(self, tmp_path) -> None:
        write_toml(
            tmp_path / "c.toml",
            {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
        )
        validate_profile(profile="default", config_path=tmp_path / "c.toml")

    def test_group_with_webdav_raises(self, tmp_path) -> None:
        write_toml(
            tmp_path / "c.toml",
            {
                "default": {
                    "api_key": "k",
                    "library_id": "1",
                    "library_type": "group",
                    "webdav": {"url": "https://x", "username": "u", "password": "p"},
                }
            },
        )
        with pytest.raises(UnsupportedLibraryTypeError):
            validate_profile(profile="default", config_path=tmp_path / "c.toml")
