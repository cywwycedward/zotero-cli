"""Integration tests for feed queries using real zotero_test.sqlite fixture."""
from __future__ import annotations

from pathlib import Path

import pytest

from zotero_cli.adapters.sqlite_reader import SQLiteReader
from zotero_cli.models.config import SQLiteConfig
from zotero_cli.models.errors import FeedNotFoundError
from zotero_cli.services.feed_service import FeedService

FIXTURE = Path(__file__).parent.parent / "fixtures" / "zotero_test.sqlite"


@pytest.fixture
def reader() -> SQLiteReader:
    if not FIXTURE.exists():
        pytest.skip("zotero_test.sqlite fixture not found")
    return SQLiteReader(SQLiteConfig(path=str(FIXTURE)))


@pytest.fixture
def svc(reader: SQLiteReader) -> FeedService:
    return FeedService(reader)


class TestFeedList:
    def test_lists_feeds(self, svc: FeedService) -> None:
        feeds = svc.list_feeds()
        assert len(feeds) == 1
        assert feeds[0].name == "Test Feed"
        assert feeds[0].total_count == 5

    def test_unread_count(self, svc: FeedService) -> None:
        feeds = svc.list_feeds()
        # 1001, 1003, 1005 have NULL readTime → 3 unread
        assert feeds[0].unread_count == 3


class TestFeedItems:
    def test_all_items(self, svc: FeedService) -> None:
        items = svc.list_items(10)
        assert len(items) == 4  # 4 dated + 1 undated excluded by default

    def test_date_filter_year(self, svc: FeedService) -> None:
        items = svc.list_items(10, date_filter="2024")
        # 1001, 1002, 1003 are in 2024; 1004 is 2023; 1005 is undated
        assert len(items) == 3

    def test_include_undated(self, svc: FeedService) -> None:
        items = svc.list_items(10, date_filter="2024", include_undated=True)
        # 1001, 1002, 1003 in 2024 + 1005 undated = 4
        assert len(items) == 4

    def test_date_filter_range(self, svc: FeedService) -> None:
        items = svc.list_items(10, date_filter="2023-12..2024-06")
        # 1001, 1002, 1003, 1004 (2023-12-31) = 4
        assert len(items) == 4

    def test_creators_attached(self, svc: FeedService) -> None:
        items = svc.list_items(10)
        i1001 = next(it for it in items if it.item_id == 1001)
        assert len(i1001.creators) == 1
        assert i1001.creators[0].last_name == "Doe"

    def test_undated_item_has_no_date_sql(self, svc: FeedService) -> None:
        items = svc.list_items(10, include_undated=True)
        i1005 = next(it for it in items if it.item_id == 1005)
        assert i1005.date_sql == "" or i1005.date_sql is None


class TestFeedNotFoundIntegration:
    def test_list_items_unknown_feed_raises(self, svc: FeedService) -> None:
        with pytest.raises(FeedNotFoundError):
            svc.list_items(99999)
