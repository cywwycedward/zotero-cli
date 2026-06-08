"""Tests for webdav_client.py core functions (zip, prop, md5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest

from zotero_cli.adapters.webdav_client import (
    WebDAVStorage,
    _build_prop_xml,
    _build_zip,
    _compute_md5,
    _parse_prop_xml,
    upload_attachment_webdav,
)
from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.config import WebDAVConfig
from zotero_cli.models.errors import (
    FileNotFoundCLIError,
    WebdavConnectionError,
    WebdavPropInvalidError,
)


class TestBuildZip:
    def test_produces_valid_zip_with_raw_filename(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_text("fake pdf content")
        data = _build_zip(pdf)
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert len(names) == 1
            assert names[0] == "test.pdf"  # raw filename, not base64


class TestComputeMd5:
    def test_returns_32_char_hex(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_text("hello")
        result = _compute_md5(pdf)
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)


class TestPropXml:
    def test_round_trip(self) -> None:
        raw = _build_prop_xml(1717584321000, "d41d8cd98f00b204e9800998ecf8427e")
        parsed = _parse_prop_xml(raw)
        assert parsed["mtime_ms"] == 1717584321000
        assert parsed["md5"] == "d41d8cd98f00b204e9800998ecf8427e"

    def test_parse_invalid_xml_raises(self) -> None:
        with pytest.raises(WebdavPropInvalidError):
            _parse_prop_xml(b"not xml")

    def test_build_has_required_elements(self) -> None:
        raw = _build_prop_xml(123, "abc")
        text = raw.decode("utf-8")
        assert "properties" in text
        assert 'version="1"' in text
        assert "<mtime>123</mtime>" in text
        assert "<hash>abc</hash>" in text


# ── WebDAVStorage class tests ────────────────────────────────────────────


def _make_config(**overrides: object) -> WebDAVConfig:
    defaults = {"url": "https://dav.example.com", "username": "u", "password": "p"}
    defaults.update(overrides)
    return WebDAVConfig(**defaults)  # type: ignore[arg-type]


class TestWebDAVStorageInit:
    def test_init_passes_config_to_webdav4_client(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        config = _make_config(timeout=60, verify_ssl=False)
        storage = WebDAVStorage(config)

        mock_cls.assert_called_once_with(
            base_url="https://dav.example.com",
            auth=("u", "p"),
            timeout=60,
            verify=False,
        )
        assert storage is not None

    def test_storage_path_property_returns_config_value(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        config = _make_config(storage_path="/my/path")
        storage = WebDAVStorage(config)
        assert storage.storage_path == "/my/path"


class TestWebDAVStorageFullPath:
    def test_full_path_valid_key_builds_correct_path(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        storage = WebDAVStorage(_make_config(storage_path="/zotero"))
        assert storage._full_path("ABC123.zip") == "/zotero/ABC123.zip"

    def test_full_path_invalid_key_raises_valueerror(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        storage = WebDAVStorage(_make_config())
        with pytest.raises(ValueError, match="Invalid Zotero key"):
            storage._full_path("bad-key.zip")

    def test_full_path_empty_storage_path_uses_root(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        config = _make_config(storage_path="")
        storage = WebDAVStorage(config)
        assert storage._full_path("ABC123.zip") == "/ABC123.zip"


class TestWebDAVStorageEnsureDir:
    def test_ensure_storage_dir_exists_no_mkcol(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        storage = WebDAVStorage(_make_config())

        storage.ensure_storage_dir()

        mock_client.exists.assert_called_once_with("/zotero")
        mock_client.mkdir.assert_not_called()

    def test_ensure_storage_dir_not_exists_creates(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        mock_client.exists.side_effect = Exception("404")
        storage = WebDAVStorage(_make_config())

        storage.ensure_storage_dir()

        mock_client.mkdir.assert_called_once_with("/zotero")

    def test_ensure_storage_dir_empty_path_skips(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        storage = WebDAVStorage(_make_config(storage_path=""))

        storage.ensure_storage_dir()

        mock_client.exists.assert_not_called()
        mock_client.mkdir.assert_not_called()


class TestWebDAVStoragePut:
    def test_put_zip_success(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        storage = WebDAVStorage(_make_config())

        storage.put_zip("ABC123", b"zipdata")

        mock_client.upload_fileobj.assert_called_once()
        args, kwargs = mock_client.upload_fileobj.call_args
        assert args[1] == "/zotero/ABC123.zip"
        assert kwargs["overwrite"] is True

    def test_put_zip_failure_raises_webdav_connection_error(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        mock_client.upload_fileobj.side_effect = Exception("connection refused")
        storage = WebDAVStorage(_make_config())

        with pytest.raises(WebdavConnectionError, match="Failed to upload zip"):
            storage.put_zip("ABC123", b"zipdata")

    def test_put_prop_success(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        storage = WebDAVStorage(_make_config())

        storage.put_prop("ABC123", b"propdata")

        mock_client.upload_fileobj.assert_called_once()
        args, _ = mock_client.upload_fileobj.call_args
        assert args[1] == "/zotero/ABC123.prop"

    def test_put_prop_failure_raises_webdav_connection_error(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        mock_client.upload_fileobj.side_effect = Exception("timeout")
        storage = WebDAVStorage(_make_config())

        with pytest.raises(WebdavConnectionError, match="Failed to upload prop"):
            storage.put_prop("ABC123", b"propdata")


class TestWebDAVStorageDeleteGet:
    def test_delete_file_success(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        storage = WebDAVStorage(_make_config())

        storage.delete_file("ABC123", "zip")

        mock_client.remove.assert_called_once_with("/zotero/ABC123.zip")

    def test_delete_file_exception_silently_ignored(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        mock_client.remove.side_effect = Exception("404 Not Found")
        storage = WebDAVStorage(_make_config())

        # Should not raise
        storage.delete_file("ABC123", "zip")

    def test_get_prop_found_returns_bytes(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value

        def fake_download(path, buf):
            buf.write(b"<properties/>")

        mock_client.download_fileobj.side_effect = fake_download
        storage = WebDAVStorage(_make_config())

        result = storage.get_prop("ABC123")

        assert result == b"<properties/>"
        mock_client.download_fileobj.assert_called_once()

    def test_get_prop_not_found_returns_none(self, mocker: object) -> None:
        mock_cls = mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        mock_client = mock_cls.return_value
        mock_client.download_fileobj.side_effect = Exception("404")
        storage = WebDAVStorage(_make_config())

        result = storage.get_prop("ABC123")

        assert result is None

    def test_check_md5_match_returns_true(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        storage = WebDAVStorage(_make_config())
        prop_xml = _build_prop_xml(1000, "d41d8cd98f00b204e9800998ecf8427e")
        mocker.patch.object(storage, "get_prop", return_value=prop_xml)

        assert storage.check_md5("ABC123", "d41d8cd98f00b204e9800998ecf8427e") is True

    def test_check_md5_mismatch_returns_false(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        storage = WebDAVStorage(_make_config())
        prop_xml = _build_prop_xml(1000, "aaaa")
        mocker.patch.object(storage, "get_prop", return_value=prop_xml)

        assert storage.check_md5("ABC123", "bbbb") is False

    def test_check_md5_no_prop_returns_false(self, mocker: object) -> None:
        mocker.patch("zotero_cli.adapters.webdav_client.WebDAVClient")  # type: ignore[union-attr]
        storage = WebDAVStorage(_make_config())
        mocker.patch.object(storage, "get_prop", return_value=None)

        assert storage.check_md5("ABC123", "anything") is False


# ── upload_attachment_webdav tests ───────────────────────────────────────


class TestUploadAttachmentWebdav:
    """Tests for the full 6-step WebDAV upload flow."""

    @pytest.fixture()
    def pdf_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "test.pdf"
        f.write_text("fake pdf content")
        return f

    @pytest.fixture()
    def mock_storage(self) -> MagicMock:
        s = MagicMock(spec=WebDAVStorage)
        s._full_path.side_effect = lambda suffix: f"/zotero/{suffix}"
        return s

    @pytest.fixture()
    def mock_api(self) -> MagicMock:
        return create_autospec(ZoteroAPI, instance=True)

    def test_upload_new_attachment_full_success(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        mock_api.create_items.return_value = {
            "successful": [{"key": "NEWKEY11"}],
        }

        result = upload_attachment_webdav(
            mock_storage, "PARENT01", pdf_file, mock_api, title="My PDF"
        )

        assert result["backend"] == "webdav"
        assert len(result["uploaded"]) == 1
        assert result["uploaded"][0]["attachment_key"] == "NEWKEY11"
        assert result["uploaded"][0]["parent_item_key"] == "PARENT01"
        assert result["uploaded"][0]["file"] == "test.pdf"
        assert result["failed"] == []
        assert result["unchanged"] == []
        mock_storage.ensure_storage_dir.assert_called_once()
        mock_storage.put_zip.assert_called_once()
        mock_storage.put_prop.assert_called_once()

    def test_upload_reuse_key_unchanged_md5_match(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        md5_hex = _compute_md5(pdf_file)
        mock_storage.check_md5.return_value = True

        result = upload_attachment_webdav(
            mock_storage, "PARENT01", pdf_file, mock_api, reuse_key="EXIST001"
        )

        assert len(result["unchanged"]) == 1
        assert result["unchanged"][0]["attachment_key"] == "EXIST001"
        assert result["unchanged"][0]["md5"] == md5_hex
        assert result["uploaded"] == []
        mock_storage.put_zip.assert_not_called()

    def test_upload_reuse_key_force_skips_md5(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        result = upload_attachment_webdav(
            mock_storage,
            "PARENT01",
            pdf_file,
            mock_api,
            reuse_key="EXIST001",
            force=True,
        )

        assert len(result["uploaded"]) == 1
        assert result["uploaded"][0]["attachment_key"] == "EXIST001"
        mock_storage.check_md5.assert_not_called()

    def test_upload_file_not_found_raises(
        self, tmp_path: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        missing = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileNotFoundCLIError, match="File not found"):
            upload_attachment_webdav(mock_storage, "PARENT01", missing, mock_api)

    def test_upload_api_create_failure_returns_failed(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        mock_api.create_items.return_value = {"successful": []}

        result = upload_attachment_webdav(mock_storage, "PARENT01", pdf_file, mock_api)

        assert len(result["failed"]) == 1
        assert result["failed"][0]["code"] == "API_SERVER_ERROR"
        assert result["uploaded"] == []

    def test_upload_ensure_dir_failure_returns_failed(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        mock_api.create_items.return_value = {
            "successful": [{"key": "NEWKEY11"}],
        }
        mock_storage.ensure_storage_dir.side_effect = Exception("PROPFIND failed")

        result = upload_attachment_webdav(mock_storage, "PARENT01", pdf_file, mock_api)

        assert len(result["failed"]) == 1
        assert result["failed"][0]["code"] == "WEBDAV_CONNECTION_ERROR"
        assert "storage dir" in result["failed"][0]["message"]

    def test_upload_put_zip_failure_rollback_deletes_attachment(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        mock_api.create_items.return_value = {
            "successful": [{"key": "NEWKEY11"}],
        }
        mock_storage.put_zip.side_effect = WebdavConnectionError("upload failed")

        result = upload_attachment_webdav(mock_storage, "PARENT01", pdf_file, mock_api)

        assert len(result["failed"]) == 1
        assert "zip" in result["failed"][0]["message"]
        # Rollback: attachment should be deleted since this is a new key
        mock_api.delete_item.assert_called_once_with({"key": "NEWKEY11"})

    def test_upload_put_prop_failure_rollback_deletes_zip_and_attachment(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        mock_api.create_items.return_value = {
            "successful": [{"key": "NEWKEY11"}],
        }
        mock_storage.put_prop.side_effect = WebdavConnectionError("prop upload failed")

        result = upload_attachment_webdav(mock_storage, "PARENT01", pdf_file, mock_api)

        assert len(result["failed"]) == 1
        assert "prop" in result["failed"][0]["message"]
        # Rollback: zip is deleted
        mock_storage.delete_file.assert_any_call("NEWKEY11", "zip")
        # Rollback: attachment is deleted (new key)
        mock_api.delete_item.assert_called_once_with({"key": "NEWKEY11"})

    def test_upload_reuse_key_put_zip_failure_no_api_delete(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        mock_storage.put_zip.side_effect = WebdavConnectionError("upload failed")

        result = upload_attachment_webdav(
            mock_storage,
            "PARENT01",
            pdf_file,
            mock_api,
            reuse_key="EXIST001",
            force=True,
        )

        assert len(result["failed"]) == 1
        # reuse_key: should NOT delete the existing attachment
        mock_api.delete_item.assert_not_called()

    def test_upload_non_zotero_api_uses_temp_key(
        self, pdf_file: Path, mock_storage: MagicMock
    ) -> None:
        """When api is not a ZoteroAPI instance, uses ATT_TEMP key (test mode)."""
        fake_api = MagicMock()
        result = upload_attachment_webdav(mock_storage, "PARENT01", pdf_file, fake_api)

        assert len(result["uploaded"]) == 1
        assert result["uploaded"][0]["attachment_key"] == "ATT_TEMP"

    def test_upload_put_prop_failure_reuse_key_no_attachment_delete(
        self, pdf_file: Path, mock_storage: MagicMock, mock_api: MagicMock
    ) -> None:
        """put_prop failure with reuse_key: rollback deletes zip but not attachment."""
        mock_storage.put_prop.side_effect = WebdavConnectionError("prop failed")

        result = upload_attachment_webdav(
            mock_storage,
            "PARENT01",
            pdf_file,
            mock_api,
            reuse_key="EXIST001",
            force=True,
        )

        assert len(result["failed"]) == 1
        mock_storage.delete_file.assert_any_call("EXIST001", "zip")
        mock_api.delete_item.assert_not_called()
