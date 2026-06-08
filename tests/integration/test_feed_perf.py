"""Performance test: 1000 feed items + date filter < 300ms (DEVELOPMENT.md §9.5)."""
from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.fixtures.build_sqlite import build_with_n_items
from zotero_cli.adapters.sqlite_reader import SQLiteReader
from zotero_cli.models.config import SQLiteConfig
from zotero_cli.services.feed_service import FeedService

PERF_DB = Path(__file__).parent.parent / "fixtures" / "perf_test.sqlite"


@pytest.fixture(scope="module")
def perf_svc() -> Generator[FeedService, None, None]:
    build_with_n_items(PERF_DB, n=1000)
    reader = SQLiteReader(SQLiteConfig(path=str(PERF_DB)))
    yield FeedService(reader)
    reader.close()
    PERF_DB.unlink(missing_ok=True)


class TestFeedPerformance:
    def test_1000_items_date_filter_under_300ms(self, perf_svc: FeedService) -> None:
        start = time.perf_counter()
        items = perf_svc.list_items(1, date_filter="2024-06", limit=1000)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert len(items) > 0
        assert elapsed_ms < 300, f"Query took {elapsed_ms:.0f}ms, expected < 300ms"

    def test_1000_items_no_filter_under_300ms(self, perf_svc: FeedService) -> None:
        start = time.perf_counter()
        items = perf_svc.list_items(1, limit=1000)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert len(items) == 1000
        assert elapsed_ms < 300, f"Query took {elapsed_ms:.0f}ms, expected < 300ms"
