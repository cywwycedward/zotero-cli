"""Unit tests for feed commands — focuses on --quiet, error paths, field filter."""
from __future__ import annotations

from zotero_cli.models.feed import FeedItem, FeedSummary


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
