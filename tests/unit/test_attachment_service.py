from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.errors import (
    CLIError,
    FileNotFoundCLIError,
    MutuallyExclusiveArgsError,
    UnsupportedLibraryTypeError,
)
from zotero_cli.services.attachment_service import (
    AttachmentService,
    _format_webdav_result,
    _format_zfs_result,
    _merge_attach_result,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def zfs_profile() -> ProfileConfig:
    return ProfileConfig(api_key="k", library_id="123", library_type="user")


@pytest.fixture
def webdav_profile() -> ProfileConfig:
    return ProfileConfig(
        api_key="k",
        library_id="123",
        library_type="user",
        webdav={"url": "https://dav.example.com", "username": "u", "password": "p"},
    )


@pytest.fixture
def group_webdav_profile() -> ProfileConfig:
    """Group library with webdav — invalid at Config level, but we bypass that
    validator to test the service-level guard."""
    p = ProfileConfig(
        api_key="k",
        library_id="123",
        library_type="user",
        webdav={"url": "https://dav.example.com", "username": "u", "password": "p"},
    )
    # Force library_type to group after construction so Config validator doesn't block us.
    object.__setattr__(p, "library_type", "group")
    return p


def _make_service(
    profile: ProfileConfig,
    *,
    backend: str = "zfs",
    mock_api: MagicMock | None = None,
) -> tuple[AttachmentService, MagicMock]:
    """Build an AttachmentService with mocked ZoteroAPI and _select_backend."""
    api = mock_api or MagicMock()
    with (
        patch("zotero_cli.services.attachment_service._select_backend", return_value=backend),
        patch("zotero_cli.services.attachment_service.ZoteroAPI", return_value=api),
    ):
        svc = AttachmentService(profile)
    return svc, api


# ── TestAttachmentServiceInit ────────────────────────────────────────────


class TestAttachmentServiceInit:
    def test_init_zfs_backend_no_webdav_config(self, zfs_profile: ProfileConfig) -> None:
        svc, _api = _make_service(zfs_profile, backend="zfs")
        assert svc.backend == "zfs"

    def test_init_webdav_backend_with_webdav_config(self, webdav_profile: ProfileConfig) -> None:
        svc, _api = _make_service(webdav_profile, backend="webdav")
        assert svc.backend == "webdav"

    def test_backend_property(self, zfs_profile: ProfileConfig) -> None:
        svc, _ = _make_service(zfs_profile, backend="zfs")
        assert svc.backend == "zfs"


# ── TestAttachmentServiceAttach ──────────────────────────────────────────


class TestAttachmentServiceAttach:
    def test_attach_group_webdav_raises_unsupported(
        self, group_webdav_profile: ProfileConfig
    ) -> None:
        svc, _ = _make_service(group_webdav_profile, backend="webdav")
        with pytest.raises(UnsupportedLibraryTypeError, match="not supported for group"):
            svc.attach("PARENT1", Path("file.pdf"))

    def test_attach_zfs_force_raises_mutually_exclusive(self, zfs_profile: ProfileConfig) -> None:
        svc, _ = _make_service(zfs_profile, backend="zfs")
        with pytest.raises(MutuallyExclusiveArgsError, match="--force"):
            svc.attach("PARENT1", Path("file.pdf"), force=True)

    def test_attach_validates_reuse_key_exists(
        self, webdav_profile: ProfileConfig, tmp_path: Path
    ) -> None:
        svc, api = _make_service(webdav_profile, backend="webdav")
        f = tmp_path / "a.pdf"
        f.write_bytes(b"data")

        # When reuse_key is given, _api.item(reuse_key) is called first.
        with (
            patch("zotero_cli.services.attachment_service.WebDAVStorage"),
            patch(
                "zotero_cli.services.attachment_service.upload_attachment_webdav",
                return_value={"uploaded": [], "unchanged": [], "failed": [], "backend": "webdav"},
            ),
        ):
            svc.attach("PARENT1", f, reuse_key="RKEY")
        api.item.assert_called_once_with("RKEY")


# ── TestAttachZfs ────────────────────────────────────────────────────────


class TestAttachZfs:
    def test_attach_zfs_success_simple(self, zfs_profile: ProfileConfig, tmp_path: Path) -> None:
        svc, api = _make_service(zfs_profile, backend="zfs")
        f = tmp_path / "paper.pdf"
        f.write_bytes(b"hello")

        api.attachment_simple.return_value = {
            "success": {"0": "ATT99"},
            "unchanged": {},
            "failed": {},
        }
        result = svc.attach("P1", f)
        api.attachment_simple.assert_called_once_with([str(f)], parentid="P1")
        assert result["data"]["backend"] == "zfs"

    def test_attach_zfs_with_title_uses_attachment_both(
        self, zfs_profile: ProfileConfig, tmp_path: Path
    ) -> None:
        svc, api = _make_service(zfs_profile, backend="zfs")
        f = tmp_path / "data.csv"
        f.write_bytes(b"1,2,3")

        api.attachment_both.return_value = {
            "success": {"0": "ATT5"},
            "unchanged": {},
            "failed": {},
        }
        svc.attach("P1", f, title="My Data")
        api.attachment_both.assert_called_once_with([("My Data", str(f))], parentid="P1")

    def test_attach_zfs_reuse_key_item_template_and_upload(
        self, zfs_profile: ProfileConfig, tmp_path: Path
    ) -> None:
        """ZFS --reuse-key: builds item_template with existing md5 and calls
        upload_attachments([tpl], parentid=None).  pyzotero 1.13.1 sends
        If-Match on the md5, fixing issue #322."""
        svc, api = _make_service(zfs_profile, backend="zfs")
        f = tmp_path / "reuse.pdf"
        f.write_bytes(b"reused content")

        # The template returned by the mock — must be a real dict, not MagicMock
        tpl = {
            "itemType": "attachment",
            "linkMode": "imported_file",
            "title": "",
            "filename": "",
            "contentType": "",
            "charset": "",
            "md5": "",
            "mtime": 0,
        }
        api.item_template.return_value = tpl
        api.item.return_value = {"key": "RKEY1", "data": {"md5": "abc123"}}
        api.upload_attachments.return_value = {
            "success": {"0": "RKEY1"},
            "unchanged": {},
            "failed": {},
        }

        result = svc.attach("P1", f, reuse_key="RKEY1")

        # Verify the template was built correctly
        # item() is called twice: once in attach() for validation (line ~70),
        # once in _attach_zfs() to read existing md5 (line ~102).
        assert api.item.call_count == 2
        api.item.assert_any_call("RKEY1")
        api.item_template.assert_called_once_with("attachment", "imported_file")
        # upload_attachments called with tpl containing key + md5, parentid=None
        api.upload_attachments.assert_called_once()
        call_args, call_kwargs = api.upload_attachments.call_args
        sent_tpls = call_args[0]
        assert len(sent_tpls) == 1
        assert sent_tpls[0]["key"] == "RKEY1"
        assert sent_tpls[0]["md5"] == "abc123"
        assert sent_tpls[0]["filename"] == str(f)
        assert call_kwargs.get("parentid") is None
        assert result["data"]["backend"] == "zfs"

    def test_attach_zfs_file_not_found_raises(self, zfs_profile: ProfileConfig) -> None:
        svc, _ = _make_service(zfs_profile, backend="zfs")
        with pytest.raises(FileNotFoundCLIError, match="File not found"):
            svc.attach("P1", Path("/nonexistent/file.pdf"))


# ── TestAttachWebdav ─────────────────────────────────────────────────────


class TestAttachWebdav:
    def test_attach_webdav_success(self, webdav_profile: ProfileConfig, tmp_path: Path) -> None:
        svc, _api = _make_service(webdav_profile, backend="webdav")
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"webdav-data")

        webdav_result: dict[str, Any] = {
            "uploaded": [{"attachment_key": "WATT1", "file": "doc.pdf"}],
            "unchanged": [],
            "failed": [],
            "backend": "webdav",
        }
        with (
            patch("zotero_cli.services.attachment_service.WebDAVStorage") as mock_stor_cls,
            patch(
                "zotero_cli.services.attachment_service.upload_attachment_webdav",
                return_value=webdav_result,
            ) as mock_upload,
        ):
            result = svc.attach("P1", f)

        mock_stor_cls.assert_called_once_with(webdav_profile.webdav)
        mock_upload.assert_called_once()
        assert result["data"]["backend"] == "webdav"
        assert len(result["data"]["uploaded"]) == 1

    def test_attach_webdav_no_config_raises(self, zfs_profile: ProfileConfig) -> None:
        """If backend is webdav but profile.webdav is None, raise."""
        svc, _ = _make_service(zfs_profile, backend="webdav")
        with pytest.raises(UnsupportedLibraryTypeError, match="WebDAV config required"):
            svc.attach("P1", Path("x.pdf"))


# ── TestAttachMulti ──────────────────────────────────────────────────────


class TestAttachMulti:
    def test_attach_multi_sequential_zfs(self, zfs_profile: ProfileConfig, tmp_path: Path) -> None:
        svc, api = _make_service(zfs_profile, backend="zfs")
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.write_bytes(b"a")
        f2.write_bytes(b"b")

        api.attachment_simple.return_value = {
            "success": {"0": "ATT_A"},
            "unchanged": {},
            "failed": {},
        }
        result = svc.attach_multi("P1", [f1, f2])
        assert api.attachment_simple.call_count == 2
        assert result["data"]["backend"] == "zfs"

    def test_attach_multi_concurrent_webdav(
        self, webdav_profile: ProfileConfig, tmp_path: Path
    ) -> None:
        svc, _api = _make_service(webdav_profile, backend="webdav")
        files = [tmp_path / f"f{i}.pdf" for i in range(3)]
        for f in files:
            f.write_bytes(b"data")

        webdav_result: dict[str, Any] = {
            "uploaded": [{"attachment_key": "W1", "file": "f.pdf"}],
            "unchanged": [],
            "failed": [],
            "backend": "webdav",
        }
        # ThreadPoolExecutor is imported locally inside attach_multi;
        # patch at its origin so the local import picks it up.
        with (
            patch("zotero_cli.services.attachment_service.WebDAVStorage"),
            patch(
                "zotero_cli.services.attachment_service.upload_attachment_webdav",
                return_value=webdav_result,
            ),
            patch("concurrent.futures.ThreadPoolExecutor") as mock_pool_cls,
        ):
            # Wire the mock executor so pool.submit returns futures with our result.
            mock_pool = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_future = MagicMock()
            mock_future.result.return_value = _format_webdav_result(webdav_result)
            mock_pool.submit.return_value = mock_future

            result = svc.attach_multi("P1", files)

        assert result["data"]["backend"] == "webdav"
        # ThreadPoolExecutor was called with max_workers=4
        mock_pool_cls.assert_called_once_with(max_workers=4)
        # submit was called once per file
        assert mock_pool.submit.call_count == 3


# ── TestFormatHelpers ────────────────────────────────────────────────────


class TestFormatHelpers:
    def test_format_zfs_result_with_success(self) -> None:
        # pyzotero success dict: iterating yields keys ("0"), not values.
        # _format_zfs_result treats each iterated element as the key string.
        raw: dict[str, Any] = {
            "success": {"0": "K1"},
            "unchanged": {},
            "failed": {},
        }
        result = _format_zfs_result(raw, "paper.pdf", "PARENT", 1024)
        assert result["data"]["backend"] == "zfs"
        assert len(result["data"]["uploaded"]) == 1
        # Dict iteration yields key "0", which becomes the attachment key.
        assert result["data"]["uploaded"][0]["key"] == "0"
        assert result["data"]["uploaded"][0]["file"] == "paper.pdf"
        assert result["data"]["uploaded"][0]["size_bytes"] == 1024
        assert result["meta_extra"]["affected_keys"] == ["0"]

    def test_format_zfs_result_with_success_list(self) -> None:
        """When 'successful' is a list of dicts (alternate pyzotero format)."""
        raw: dict[str, Any] = {
            "successful": [{"key": "K1"}],
            "unchanged": [],
            "failed": [],
        }
        result = _format_zfs_result(raw, "paper.pdf", "PARENT", 2048)
        assert len(result["data"]["uploaded"]) == 1
        assert result["data"]["uploaded"][0]["key"] == "K1"
        assert result["meta_extra"]["affected_keys"] == ["K1"]

    def test_format_zfs_result_with_failure(self) -> None:
        raw: dict[str, Any] = {
            "success": {},
            "unchanged": {},
            "failed": {"0": "err msg"},
        }
        result = _format_zfs_result(raw, "bad.pdf", "PARENT", 512)
        assert len(result["data"]["failed"]) == 1
        assert result["data"]["failed"][0]["code"] == "API_SERVER_ERROR"
        assert result["data"]["uploaded"] == []

    def test_format_webdav_result(self) -> None:
        raw: dict[str, Any] = {
            "uploaded": [{"attachment_key": "WK1", "file": "doc.pdf"}],
            "unchanged": [],
            "failed": [],
            "backend": "webdav",
        }
        result = _format_webdav_result(raw)
        assert result["data"]["backend"] == "webdav"
        assert len(result["data"]["uploaded"]) == 1
        assert result["data"]["uploaded"][0]["key"] == "WK1"
        assert result["meta_extra"]["affected_keys"] == ["WK1"]

    def test_merge_attach_result(self) -> None:
        r: dict[str, Any] = {
            "data": {
                "uploaded": [{"key": "U1"}],
                "unchanged": [{"key": "C1"}],
                "failed": [{"key": "F1"}],
            },
            "meta_extra": {"affected_keys": ["U1"]},
        }
        uploaded: list[Any] = []
        unchanged: list[Any] = []
        failed: list[Any] = []
        affected: list[str] = []
        _merge_attach_result(r, uploaded, unchanged, failed, affected)
        assert uploaded == [{"key": "U1"}]
        assert unchanged == [{"key": "C1"}]
        assert failed == [{"key": "F1"}]
        assert affected == ["U1"]
