"""tests/unit/test_doi_item_service.py"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from zotero_cli.models.errors import ApiServerError, InvalidFieldError
from zotero_cli.services.doi_item_service import DoiItemService


@pytest.fixture
def mock_api() -> MagicMock:
    api = MagicMock()
    api.item_template.return_value = {
        "itemType": "",
        "title": "",
        "creators": [],
        "date": "",
        "DOI": "",
        "url": "",
        "abstractNote": "",
        "tags": [],
        "collections": [],
        "publicationTitle": "",
        "volume": "",
        "issue": "",
        "pages": "",
        "ISSN": "",
        "publisher": "",
    }
    return api


@pytest.fixture
def mock_item_service() -> MagicMock:
    svc = MagicMock()
    svc.create.return_value = {
        "data": {
            "successful": [{"index": 0, "key": "NEWKEY", "version": 1}],
            "unchanged": [],
            "failed": [],
        },
        "meta_extra": {"affected_keys": ["NEWKEY"]},
    }
    return svc


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.source = "crossref"
    provider.fetch.return_value = {
        "type": "journal-article",
        "title": ["Test Paper"],
        "DOI": "10.1000/test",
        "author": [{"given": "A", "family": "B"}],
    }
    provider.to_zotero_item.return_value = {
        "itemType": "journalArticle",
        "title": "Test Paper",
        "DOI": "10.1000/test",
        "creators": [{"creatorType": "author", "firstName": "A", "lastName": "B"}],
    }
    return provider


@pytest.fixture
def svc(mock_api: MagicMock, mock_item_service: MagicMock, mock_provider: MagicMock) -> DoiItemService:
    return DoiItemService(api=mock_api, item_service=mock_item_service, provider=mock_provider)


class TestAddByDoi:
    def test_dry_run_does_not_create(self, svc, mock_item_service, mock_provider) -> None:
        result = svc.add_by_doi("10.1000/test", dry_run=True)
        assert result["data"]["dry_run"] is True
        assert "would_create" in result["data"]
        mock_item_service.create.assert_not_called()

    def test_dry_run_includes_metadata(self, svc, mock_api, mock_provider) -> None:
        result = svc.add_by_doi("10.1000/test", dry_run=True)
        meta = result["meta_extra"]
        assert meta["dry_run"] is True
        assert meta["source"] == "crossref"
        assert meta["normalized_doi"] == "10.1000/test"

    def test_creates_item_via_item_service(self, svc, mock_item_service, mock_provider) -> None:
        result = svc.add_by_doi("10.1000/test", dry_run=False)
        mock_item_service.create.assert_called_once()
        payload = mock_item_service.create.call_args[0][0][0]
        assert payload["itemType"] == "journalArticle"
        assert payload["title"] == "Test Paper"
        assert result["meta_extra"]["affected_keys"] == ["NEWKEY"]

    def test_tags_appended(self, svc, mock_item_service, mock_provider) -> None:
        svc.add_by_doi("10.1000/test", dry_run=False, tags=["ai", "paper"])
        payload = mock_item_service.create.call_args[0][0][0]
        assert payload["tags"] == [{"tag": "ai"}, {"tag": "paper"}]

    def test_collection_appended(self, svc, mock_item_service, mock_provider) -> None:
        svc.add_by_doi("10.1000/test", dry_run=False, collection="ABC123")
        payload = mock_item_service.create.call_args[0][0][0]
        assert payload["collections"] == ["ABC123"]

    def test_invalid_doi_raises(self, svc) -> None:
        with pytest.raises(InvalidFieldError, match="DOI"):
            svc.add_by_doi("not-a-doi")

    def test_missing_title_raises(self, svc, mock_provider) -> None:
        mock_provider.to_zotero_item.return_value = {
            "itemType": "journalArticle",
            "DOI": "10.1000/test",
        }
        with pytest.raises(ApiServerError, match="title"):
            svc.add_by_doi("10.1000/test")

    def test_missing_item_type_raises(self, svc, mock_provider) -> None:
        mock_provider.to_zotero_item.return_value = {
            "title": "Test",
            "DOI": "10.1000/test",
        }
        with pytest.raises(ApiServerError, match="itemType"):
            svc.add_by_doi("10.1000/test")

    def test_missing_doi_in_payload_raises(self, svc, mock_provider) -> None:
        mock_provider.to_zotero_item.return_value = {
            "itemType": "journalArticle",
            "title": "Test",
        }
        with pytest.raises(ApiServerError, match="DOI"):
            svc.add_by_doi("10.1000/test")

    def test_doi_url_normalized(self, svc, mock_provider) -> None:
        svc.add_by_doi("https://doi.org/10.1000/test", dry_run=True)
        mock_provider.fetch.assert_called_once_with("10.1000/test")
