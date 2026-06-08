"""Unit tests for feed commands — focuses on --quiet, error paths, field filter."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from zotero_cli.commands._runner import GlobalOptions
from zotero_cli.commands.feeds import app as feeds_app
from zotero_cli.models.errors import FeedNotFoundError
from zotero_cli.models.feed import FeedItem, FeedSummary
from zotero_cli.services.feed_service import FeedService

runner = CliRunner()


def _ctx(**overrides: Any) -> GlobalOptions:
    defaults: dict[str, Any] = {
        "profile": "default",
        "json_mode": False,
        "quiet": False,
        "config_path": None,
    }
    defaults.update(overrides)
    return GlobalOptions(**defaults)


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

    def test_feed_item_dump_contains_date(self) -> None:
        item = FeedItem(feed_id=10, item_id=1001, date_raw="2024-06-15 2024-06-15")
        d = item.model_dump()
        assert "date" in d
        assert d["date"] == "2024-06-15 2024-06-15"


class TestFeedNotFound:
    """F3: feeds items <unknown-id> must raise FEED_NOT_FOUND."""

    def test_list_items_unknown_feed_raises(self) -> None:
        mock_reader = MagicMock()
        mock_reader.feed_exists.return_value = False
        svc = FeedService(mock_reader)
        with pytest.raises(FeedNotFoundError):
            svc.list_items(99999)


class TestFeedsListCommand:
    @patch("zotero_cli.commands.feeds._get_svc")
    def test_list_feeds_success(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = [
            FeedSummary(
                libraryID=10, name="Test", url="https://example.com",
                total_count=5, unread_count=3,
            ),
        ]
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["list"], obj=_ctx())
        assert result.exit_code == 0
        assert "Test" in result.stdout

    @patch("zotero_cli.commands.feeds._get_svc")
    def test_list_feeds_quiet(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = [
            FeedSummary(
                libraryID=10, name="Test", url="https://example.com",
                total_count=5, unread_count=3,
            ),
        ]
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["list"], obj=_ctx(quiet=True))
        assert result.exit_code == 0
        assert "10" in result.stdout

    @patch("zotero_cli.commands.feeds._get_svc")
    def test_list_feeds_empty(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = []
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["list"], obj=_ctx())
        assert result.exit_code == 0


class TestFeedsShowCommand:
    @patch("zotero_cli.commands.feeds._get_svc")
    def test_show_feed_success(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = [
            FeedSummary(
                libraryID=10, name="Test", url="https://example.com",
                total_count=5, unread_count=3,
            ),
        ]
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["show", "10"], obj=_ctx())
        assert result.exit_code == 0

    @patch("zotero_cli.commands.feeds._get_svc")
    def test_show_feed_not_found(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = []
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["show", "99"], obj=_ctx())
        assert result.exit_code == 1


class TestFeedsItemsCommand:
    @patch("zotero_cli.commands.feeds.FeedService")
    @patch("zotero_cli.commands.feeds.SQLiteReader")
    @patch("zotero_cli.commands.feeds.load_config")
    def test_items_success(
        self, mock_load_config: MagicMock, mock_reader_cls: MagicMock,
        mock_svc_cls: MagicMock,
    ) -> None:
        mock_profile = MagicMock()
        mock_profile.feed_item_fields.list = ["title", "url"]
        mock_load_config.return_value = mock_profile
        mock_svc = MagicMock()
        mock_svc.list_items.return_value = [
            FeedItem(feed_id=10, item_id=1001, title="Article"),
        ]
        mock_svc_cls.return_value = mock_svc
        result = runner.invoke(feeds_app, ["items", "10"], obj=_ctx())
        assert result.exit_code == 0

    @patch("zotero_cli.commands.feeds.FeedService")
    @patch("zotero_cli.commands.feeds.SQLiteReader")
    @patch("zotero_cli.commands.feeds.load_config")
    def test_items_not_found(
        self, mock_load_config: MagicMock, mock_reader_cls: MagicMock,
        mock_svc_cls: MagicMock,
    ) -> None:
        mock_profile = MagicMock()
        mock_profile.feed_item_fields.list = ["title"]
        mock_load_config.return_value = mock_profile
        mock_svc = MagicMock()
        mock_svc.list_items.side_effect = FeedNotFoundError("Feed 99 not found")
        mock_svc_cls.return_value = mock_svc
        result = runner.invoke(feeds_app, ["items", "99"], obj=_ctx())
        assert result.exit_code == 1

    @patch("zotero_cli.commands.feeds.FeedService")
    @patch("zotero_cli.commands.feeds.SQLiteReader")
    @patch("zotero_cli.commands.feeds.load_config")
    def test_items_all_fields(
        self, mock_load_config: MagicMock, mock_reader_cls: MagicMock,
        mock_svc_cls: MagicMock,
    ) -> None:
        mock_profile = MagicMock()
        mock_load_config.return_value = mock_profile
        mock_svc = MagicMock()
        mock_svc.list_items.return_value = [
            FeedItem(
                feed_id=10, item_id=1001, title="Article",
                url="https://example.com",
            ),
        ]
        mock_svc_cls.return_value = mock_svc
        result = runner.invoke(feeds_app, ["items", "10", "--all-fields"], obj=_ctx())
        assert result.exit_code == 0
