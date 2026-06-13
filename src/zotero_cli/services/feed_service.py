"""FeedService — coordinates SQLiteReader for RSS queries."""

from __future__ import annotations

from typing import Any

from zotero_cli.adapters.sqlite_reader import SQLiteReader
from zotero_cli.models.errors import FeedNotFoundError
from zotero_cli.models.feed import FeedItem, FeedSummary
from zotero_cli.utils.date_parser import date_range_to_sql_bounds


class FeedService:
    """RSS feed read operations."""

    def __init__(self, reader: SQLiteReader) -> None:
        self._reader = reader

    @classmethod
    def from_profile(cls, profile: Any) -> FeedService:
        return cls(SQLiteReader(profile.sqlite))

    def list_feeds(self) -> list[FeedSummary]:
        rows = self._reader.list_feeds()
        return [FeedSummary(**r) for r in rows]

    def list_items(
        self,
        feed_id: int,
        *,
        date_filter: str | None = None,
        include_undated: bool = False,
        limit: int = 100,
    ) -> list[FeedItem]:
        if not self._reader.feed_exists(feed_id):
            raise FeedNotFoundError(
                f"Feed {feed_id} not found",
                hint="Use 'feeds list' to see available feeds.",
            )
        date_start = "0000-00-00"
        date_end = "9999-12-31"
        if date_filter:
            bounds = date_range_to_sql_bounds(date_filter)
            date_start = bounds.start
            date_end = bounds.end

        rows = self._reader.query_items(
            feed_id,
            date_start=date_start,
            date_end=date_end,
            include_undated=include_undated,
            limit=limit,
        )
        item_ids = [r["item_id"] for r in rows]
        item_data_map = self._reader.query_item_data(item_ids)
        creators_map = self._reader.query_creators(item_ids)
        items: list[FeedItem] = []
        for r in rows:
            iid = r["item_id"]
            dynamic = {k: v for k, v in item_data_map.get(iid, {}).items() if k != "date"}
            merged = {**dynamic, **r}
            if "abstractNote" in merged:
                merged.setdefault("abstract", merged.pop("abstractNote"))
            creators = creators_map.get(iid, [])
            merged["creators"] = [
                {
                    "first_name": c.get("firstName", ""),
                    "last_name": c.get("lastName", ""),
                    "creator_type": c.get("creatorType", ""),
                    "order_index": c.get("orderIndex", 0),
                }
                for c in creators
            ]
            items.append(FeedItem(**merged))
        return items
