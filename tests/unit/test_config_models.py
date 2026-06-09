from __future__ import annotations

import pytest
from pydantic import ValidationError

from zotero_cli.models.config import (
    Config,
    FeedFieldsConfig,
    FeedItemFieldsConfig,
    ItemFieldsConfig,
    ProfileConfig,
    SQLiteConfig,
    WebDAVConfig,
)
from zotero_cli.models.errors import (
    ConfigInvalidError,
    UnsupportedLibraryTypeError,
)

# ── Task 1: ItemFieldsConfig + FeedItemFieldsConfig ───────────────────────


class TestItemFieldsConfig:
    def test_default_list(self) -> None:
        cfg = ItemFieldsConfig()
        assert cfg.list == ["key", "title", "creators", "date", "itemType", "tags"]

    def test_override_list(self) -> None:
        cfg = ItemFieldsConfig(list=["key", "title"])
        assert cfg.list == ["key", "title"]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemFieldsConfig(list=["k"], unknown="x")  # type: ignore[call-arg]


class TestFeedItemFieldsConfig:
    def test_default_list(self) -> None:
        cfg = FeedItemFieldsConfig()
        assert cfg.list == [
            "feed_id",
            "item_id",
            "title",
            "date",
            "url",
            "read_time",
        ]

    def test_override_list(self) -> None:
        cfg = FeedItemFieldsConfig(list=["feed_id", "title"])
        assert cfg.list == ["feed_id", "title"]


class TestFeedFieldsConfig:
    def test_default_list(self) -> None:
        cfg = FeedFieldsConfig()
        assert cfg.list == ["feed_id", "name", "url", "unread_count", "total_count"]

    def test_override_list(self) -> None:
        cfg = FeedFieldsConfig(list=["feed_id", "name"])
        assert cfg.list == ["feed_id", "name"]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FeedFieldsConfig(list=["k"], unknown="x")  # type: ignore[call-arg]


# ── Task 2: WebDAVConfig + storage_path normalize ─────────────────────────


class TestWebDAVConfig:
    def test_minimal_required(self) -> None:
        cfg = WebDAVConfig(url="https://x", username="u", password="p")
        assert cfg.url == "https://x"
        assert cfg.username == "u"
        assert cfg.password == "p"
        assert cfg.storage_path == "/zotero"
        assert cfg.timeout == 120
        assert cfg.verify_ssl is True

    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("", ""),
            ("/zotero", "/zotero"),
            ("/zotero/", "/zotero"),
            ("/a/b/c", "/a/b/c"),
            ("/a/b/c/", "/a/b/c"),
        ],
    )
    def test_storage_path_normalized(self, inp: str, expected: str) -> None:
        cfg = WebDAVConfig(url="https://x", username="u", password="p", storage_path=inp)
        assert cfg.storage_path == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "/",
            "//zotero",
            "/a//b",
            "/..",
            "/a/../b",
            "no-slash",
        ],
    )
    def test_storage_path_rejected(self, bad: str) -> None:
        with pytest.raises(ConfigInvalidError):
            WebDAVConfig(url="https://x", username="u", password="p", storage_path=bad)


# ── Task 3: SQLiteConfig ──────────────────────────────────────────────────


class TestSQLiteConfig:
    def test_path_optional(self) -> None:
        cfg = SQLiteConfig()
        assert cfg.path is None

    def test_path_explicit(self) -> None:
        cfg = SQLiteConfig(path="/custom/zotero.sqlite")
        assert cfg.path == "/custom/zotero.sqlite"

    def test_default_factory_independent(self) -> None:
        a = SQLiteConfig()
        b = SQLiteConfig()
        assert a.path is None
        assert b.path is None


# ── Task 4: ProfileConfig ─────────────────────────────────────────────────


class TestProfileConfig:
    def test_minimal_user(self) -> None:
        cfg = ProfileConfig(api_key="k", library_id="123", library_type="user")
        assert cfg.api_key == "k"
        assert cfg.library_id == "123"
        assert cfg.library_type == "user"
        assert cfg.webdav is None
        assert cfg.sqlite.path is None
        assert cfg.item_fields.list[0] == "key"

    def test_with_webdav(self) -> None:
        cfg = ProfileConfig(
            api_key="k",
            library_id="123",
            library_type="user",
            webdav={"url": "https://x", "username": "u", "password": "p"},
        )  # type: ignore[call-arg]
        assert cfg.webdav is not None
        assert cfg.webdav.storage_path == "/zotero"

    def test_library_type_literal_rejects_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ProfileConfig(api_key="k", library_id="1", library_type="organization")  # type: ignore[arg-type]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProfileConfig(api_key="k", library_id="1", library_type="user", unknown_field="x")  # type: ignore[call-arg]

    def test_group_library_type_accepted(self) -> None:
        cfg = ProfileConfig(api_key="k", library_id="1", library_type="group")
        assert cfg.library_type == "group"


# -- Task 5: Config + WebDAV x library_type compat matrix


class TestConfig:
    @pytest.mark.parametrize(
        "library_type,has_webdav,ok",
        [
            ("user", False, True),
            ("user", True, True),
            ("group", False, True),
            ("group", True, False),
        ],
    )
    def test_compatibility_matrix(self, library_type, has_webdav, ok) -> None:
        profile_data: dict = {"api_key": "k", "library_id": "1", "library_type": library_type}
        if has_webdav:
            profile_data["webdav"] = {"url": "https://x", "username": "u", "password": "p"}
        if ok:
            cfg = Config(profiles={"default": profile_data})  # type: ignore[arg-type]
            assert "default" in cfg.profiles
        else:
            with pytest.raises(UnsupportedLibraryTypeError) as ei:
                Config(profiles={"default": profile_data})  # type: ignore[arg-type]
            assert "default" in (ei.value.context or {}).get("profile", "default")

    def test_multiple_profiles(self) -> None:
        cfg = Config(
            profiles={
                "default": {"api_key": "k", "library_id": "1", "library_type": "user"},
                "work": {"api_key": "k2", "library_id": "2", "library_type": "group"},
            }
        )  # type: ignore[arg-type]
        assert set(cfg.profiles) == {"default", "work"}


class TestCrossrefEmail:
    def test_default_is_none(self) -> None:
        p = ProfileConfig(api_key="k", library_id="1", library_type="user")
        assert p.crossref_email is None

    def test_valid_email(self) -> None:
        p = ProfileConfig(
            api_key="k",
            library_id="1",
            library_type="user",
            crossref_email="user@example.com",
        )
        assert p.crossref_email == "user@example.com"

    def test_empty_string_normalized_to_none(self) -> None:
        p = ProfileConfig(
            api_key="k", library_id="1", library_type="user", crossref_email=""
        )
        assert p.crossref_email is None

    def test_missing_at_sign_rejected(self) -> None:
        with pytest.raises(ConfigInvalidError):
            ProfileConfig(
                api_key="k",
                library_id="1",
                library_type="user",
                crossref_email="invalid",
            )

    def test_non_string_rejected(self) -> None:
        with pytest.raises(ConfigInvalidError, match="must be a string"):
            ProfileConfig(
                api_key="k",
                library_id="1",
                library_type="user",
                crossref_email=123,  # type: ignore[arg-type]
            )
