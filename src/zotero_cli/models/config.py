"""Configuration models per design §5. All TOML/profile/config schemas live here.

Per DEVELOPMENT.md §5.2: models/ can import error classes (pure data dependency).
"""

from __future__ import annotations

import builtins
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from zotero_cli.models.errors import ConfigInvalidError, UnsupportedLibraryTypeError

# ── Task 1: ItemFieldsConfig + FeedItemFieldsConfig ───────────────────────


class ItemFieldsConfig(BaseModel):
    """Fields to show for items list/search (design §5.2 / §7.4)."""

    model_config = ConfigDict(extra="forbid")

    list: builtins.list[str] = ["key", "title", "creators", "date", "itemType", "tags"]


class FeedItemFieldsConfig(BaseModel):
    """Fields to show for feeds items (design §5.2 / §7.4)."""

    model_config = ConfigDict(extra="forbid")

    list: builtins.list[str] = [
        "feed_id",
        "item_id",
        "title",
        "date",
        "url",
        "read_time",
    ]


# ── Task 2: WebDAVConfig + storage_path normalize ─────────────────────────


class WebDAVConfig(BaseModel):
    """WebDAV backend settings (design §5.2 / §10.1). Only valid for user libraries."""

    model_config = ConfigDict(extra="forbid")

    url: str
    storage_path: str = "/zotero"
    username: str
    password: str
    timeout: int = 120
    verify_ssl: bool = True

    @field_validator("storage_path")
    @classmethod
    def _normalize_storage_path(cls, v: str) -> str:
        if v == "":
            return v
        if not v.startswith("/"):
            raise ConfigInvalidError(
                f"storage_path must start with '/' or be empty, got: {v!r}",
                hint="Use '' for server root or '/path/to/zotero'.",
            )
        if v == "/":
            raise ConfigInvalidError(
                "storage_path cannot be '/'; use '' for server root.",
            )
        if ".." in v.split("/") or "//" in v:
            raise ConfigInvalidError(
                f"storage_path must not contain '..' or '//', got: {v!r}",
            )
        return v.rstrip("/")


# ── Task 3: SQLiteConfig ──────────────────────────────────────────────────


class SQLiteConfig(BaseModel):
    """SQLite database path. None = auto-detect (design §5.4)."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None


# ── Task 4: ProfileConfig ─────────────────────────────────────────────────


class ProfileConfig(BaseModel):
    """A single named profile holding credentials and sub-configs (design §5.2)."""

    model_config = ConfigDict(extra="forbid")

    api_key: str
    library_id: str
    library_type: Literal["user", "group"]
    webdav: WebDAVConfig | None = None
    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    item_fields: ItemFieldsConfig = Field(default_factory=ItemFieldsConfig)
    feed_item_fields: FeedItemFieldsConfig = Field(default_factory=FeedItemFieldsConfig)


# -- Task 5: Config + WebDAV x library_type compat matrix


class Config(BaseModel):
    """Top-level config holding all profiles (design §5.2)."""

    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, ProfileConfig]

    @model_validator(mode="after")
    def _check_compat_matrix(self) -> Config:
        for name, p in self.profiles.items():
            if p.library_type == "group" and p.webdav is not None:
                raise UnsupportedLibraryTypeError(
                    f"profile {name!r}: library_type='group' is incompatible with [webdav].",
                    hint="Zotero WebDAV sync does not support group libraries. "
                    "Remove [webdav] section or change library_type to 'user'.",
                    context={"profile": name, "library_type": "group"},
                )
        return self
