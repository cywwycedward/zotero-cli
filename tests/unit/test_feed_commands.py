"""Unit tests for feed commands — focuses on --quiet, error paths, field filter."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zotero_cli.models.errors import FeedNotFoundError
from zotero_cli.models.feed import FeedItem, FeedSummary
from zotero_cli.services.feed_service import FeedService


class TestFeedModelKeys:
    """F1: model_dump() must include 'key' for --quiet rendering."""

    def test_feed_summary_dump_contains_key(self) -> None:
        summary = FeedSummary(
            libraryID=10, name="Test", url="https://example.com",
            total_count=5, unread_count=3,
        )
        d = summary.model_dump()
        assert "key" in d
        assert d["key"] == "10"

    def test_feed_item_dump_contains_key(self) -> None:
        item = FeedItem(feed_id=10, item_id=1001)
        d = item.model_dump()
        assert "key" in d
        assert d["key"] == "1001"


class TestFeedNotFound:
    """F3: feeds items <unknown-id> must raise FEED_NOT_FOUND."""

    def test_list_items_unknown_feed_raises(self) -> None:
        mock_reader = MagicMock()
        mock_reader.feed_exists.return_value = False
        svc = FeedService(mock_reader)
        with pytest.raises(FeedNotFoundError):
            svc.list_items(99999)
