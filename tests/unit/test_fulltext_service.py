from __future__ import annotations

from unittest.mock import MagicMock

from zotero_cli.services.fulltext_service import FulltextService


def test_get_returns_fulltext_data_and_metadata() -> None:
    api = MagicMock()
    api.fulltext_item.return_value = {
        "content": "Full-text content",
        "indexedPages": 12,
        "totalPages": 12,
    }

    result = FulltextService(api).get("ATT1")

    assert result["data"] == {
        "key": "ATT1",
        "content": "Full-text content",
        "indexedPages": 12,
        "totalPages": 12,
    }
    assert result["meta_extra"] == {
        "item_key": "ATT1",
        "content_length": len("Full-text content"),
    }
    api.fulltext_item.assert_called_once_with("ATT1")
