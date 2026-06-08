"""Config service: orchestration layer (no direct I/O).

Per DEVELOPMENT.md §5.2: all file I/O is delegated to adapters/config_store.
This module only composes calls and applies business rules.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from zotero_cli.adapters.config_store import (
    default_config_path,
    detect_sqlite_db,
    read_toml,
)
from zotero_cli.models.config import Config, ProfileConfig
from zotero_cli.models.errors import ConfigInvalidError, InvalidProfileError

# ── ENV override mapping (design §5.3) ─────────────────────────────────────

# Maps env suffix → (field_path_tuple, value_converter)
# Field path: nested keys to set in profile dict.
# Converter: transforms string env value to the correct type.
_ENV_FIELD_MAP: dict[str, tuple[list[str], Callable[[str], Any] | None]] = {
    "API_KEY": (["api_key"], None),
    "LIBRARY_ID": (["library_id"], None),
    "LIBRARY_TYPE": (["library_type"], None),
    "WEBDAV_URL": (["webdav", "url"], None),
    "WEBDAV_STORAGE_PATH": (["webdav", "storage_path"], None),
    "WEBDAV_USERNAME": (["webdav", "username"], None),
    "WEBDAV_PASSWORD": (["webdav", "password"], None),
    "WEBDAV_TIMEOUT": (["webdav", "timeout"], int),
    "WEBDAV_VERIFY_SSL": (
        ["webdav", "verify_ssl"],
        lambda v: v.lower() in ("true", "1", "yes"),
    ),
    "SQLITE_PATH": (["sqlite", "path"], None),
    "ITEM_FIELDS_LIST": (
        ["item_fields", "list"],
        lambda v: [x.strip() for x in v.split(",") if x.strip()],
    ),
    "FEED_ITEM_FIELDS_LIST": (
        ["feed_item_fields", "list"],
        lambda v: [x.strip() for x in v.split(",") if x.strip()],
    ),
}


def _apply_env_overrides(profile_name: str, profile_dict: dict[str, Any]) -> dict[str, Any]:
    """Apply ZOTERO_CLI_<PROFILE>_<KEY> environment overrides to a profile dict."""
    prefix = f"ZOTERO_CLI_{profile_name.upper()}_"
    result = dict(profile_dict)

    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        suffix = env_key[len(prefix) :]
        mapping = _ENV_FIELD_MAP.get(suffix)
        if mapping is None:
            continue
        field_path, converter = mapping
        value: Any = env_val
        if converter is not None:
            value = converter(env_val)
        _set_nested(result, field_path, value)

    return result


def _set_nested(d: dict[str, Any], path: list[str], value: Any) -> None:
    """Set a nested dict value, creating intermediate dicts as needed."""
    for key in path[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    d[path[-1]] = value


def _fill_sqlite_default(profile_dict: dict[str, Any]) -> dict[str, Any]:
    """Auto-detect SQLite path if not explicitly set."""
    sqlite = profile_dict.get("sqlite", {})
    if isinstance(sqlite, dict) and sqlite.get("path"):
        return profile_dict
    detected = detect_sqlite_db()
    if detected:
        result = dict(profile_dict)
        if "sqlite" not in result or not isinstance(result["sqlite"], dict):
            result["sqlite"] = {}
        result["sqlite"]["path"] = detected
        return result
    return profile_dict


# ── Public API ─────────────────────────────────────────────────────────────


def load_config(
    profile: str,
    *,
    config_path: Path | None = None,
) -> ProfileConfig:
    """Load and validate a single profile.

    Pipeline: read TOML → check profile exists → apply env overrides →
    auto-detect SQLite path → pydantic validation (incl. compat matrix).
    """
    path = config_path or default_config_path()
    raw = read_toml(path)

    if profile not in raw:
        available = ", ".join(sorted(raw)) or "(none)"
        raise InvalidProfileError(
            f"Profile {profile!r} not found in {path}",
            hint=f"Available profiles: {available}",
        )

    profile_dict: dict[str, Any] = dict(raw[profile])
    profile_dict = _apply_env_overrides(profile, profile_dict)
    profile_dict = _fill_sqlite_default(profile_dict)

    try:
        cfg = Config(profiles={profile: profile_dict})  # type: ignore[dict-item]  # pydantic coerces dicts
    except ValidationError as exc:
        raise ConfigInvalidError(
            str(exc),
            hint="Check your config file values and types.",
        ) from exc
    return cfg.profiles[profile]


def validate_profile(
    profile: str,
    *,
    config_path: Path | None = None,
) -> None:
    """Validate that a profile exists and passes all checks (incl. compat matrix)."""
    load_config(profile=profile, config_path=config_path)
