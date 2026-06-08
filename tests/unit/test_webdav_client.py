"""Tests for webdav_client.py core functions (zip, prop, md5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from zotero_cli.adapters.webdav_client import (
    _build_prop_xml,
    _build_zip,
    _compute_md5,
    _parse_prop_xml,
)
from zotero_cli.models.errors import WebdavPropInvalidError


class TestBuildZip:
    def test_produces_valid_zip_with_stored_compression(self, tmp_path: Path) -> None:
        pdf = tmp_path / "test.pdf"
        pdf.write_text("fake pdf content")
        data = _build_zip(pdf)
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert len(zf.namelist()) == 1
            info = zf.getinfo(zf.namelist()[0])
            assert info.compress_type == zipfile.ZIP_STORED


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
