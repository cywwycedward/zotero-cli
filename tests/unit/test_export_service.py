from unittest.mock import MagicMock

import pytest

from zotero_cli.services.export_service import ExportService


@pytest.fixture
def svc() -> ExportService:
    return ExportService(MagicMock())


class TestExport:
    def test_returns_raw_bytes(self, svc) -> None:
        svc._api.export_items.return_value = b"@article{key, title={Test}}"
        result = svc.export("bibtex")
        assert result["data"] == b"@article{key, title={Test}}"
        assert result["meta_extra"]["format"] == "bibtex"
        assert result["meta_extra"]["byte_size"] == len(b"@article{key, title={Test}}")

    def test_passes_collection_and_tag_filters(self, svc) -> None:
        svc._api.export_items.return_value = b""
        svc.export("ris", collection="COLL1", tag="nlp")
        svc._api.export_items.assert_called_once_with(
            "ris", collection="COLL1", tag="nlp", limit=100,
        )

    def test_passes_limit(self, svc) -> None:
        svc._api.export_items.return_value = b""
        svc.export("ris", limit=25)
        svc._api.export_items.assert_called_once_with(
            "ris", collection=None, tag=None, limit=25,
        )

    def test_empty_export(self, svc) -> None:
        svc._api.export_items.return_value = b""
        result = svc.export("csljson")
        assert result["data"] == b""
        assert result["meta_extra"]["byte_size"] == 0
