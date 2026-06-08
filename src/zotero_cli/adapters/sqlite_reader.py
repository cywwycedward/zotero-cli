"""SQLiteReader — read-only access to zotero.sqlite (design §11.1)."""
from __future__ import annotations

import sqlite3
from typing import Any

from zotero_cli.models.config import SQLiteConfig
from zotero_cli.models.errors import SqliteNotFoundError, SqliteSchemaIncompatibleError

REQUIRED_TABLES = {"items", "feedItems", "feeds", "fields", "itemData", "itemDataValues"}
REQUIRED_FEEDITEMS_COLUMNS = {"guid", "readTime", "translatedTime"}
FIELD_NAMES = {"title", "date", "url", "abstractNote"}


class SQLiteReader:
    """Read-only Zotero SQLite connection. Caches field IDs on init."""

    def __init__(self, config: SQLiteConfig) -> None:
        if config.path is None:
            raise SqliteNotFoundError(
                "SQLite path not configured and auto-detection failed",
                hint="Set [<profile>.sqlite] path in config or set ZOTERO_DATA_DIR.",
            )
        uri = f"file:{config.path}?mode=ro&nolock=1"
        try:
            self._conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        except sqlite3.OperationalError as exc:
            raise SqliteNotFoundError(
                f"Cannot open SQLite database: {config.path}",
                hint="Check the file exists and is readable.",
                cause=exc,
            ) from exc
        self._conn.row_factory = sqlite3.Row
        self._field_ids: dict[str, int] = {}
        self._check_schema()
        self._cache_field_ids()

    def _check_schema(self) -> None:
        """Verify required tables exist."""
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing = {r[0] for r in cur.fetchall()}
        missing = REQUIRED_TABLES - existing
        if missing:
            raise SqliteSchemaIncompatibleError(
                f"Missing required tables: {missing}",
                hint="This database may not be a Zotero database.",
            )
        # Check required feedItems columns
        cur = self._conn.execute("PRAGMA table_info(feedItems)")
        fi_cols = {r[1] for r in cur.fetchall()}
        missing_cols = REQUIRED_FEEDITEMS_COLUMNS - fi_cols
        if missing_cols:
            raise SqliteSchemaIncompatibleError(
                f"feedItems table missing required columns: {missing_cols}",
                hint="Zotero database may be from an older version without RSS support.",
            )

    def _cache_field_ids(self) -> None:
        cur = self._conn.execute(
            "SELECT fieldID, fieldName FROM fields WHERE fieldName IN (?, ?, ?, ?)",
            tuple(FIELD_NAMES),
        )
        for row in cur.fetchall():
            self._field_ids[row["fieldName"]] = row["fieldID"]

    def _field_id(self, name: str) -> int:
        return self._field_ids[name]

    def list_feeds(self) -> list[dict[str, Any]]:
        sql = """
        SELECT
            f.libraryID, f.name, f.url, f.lastUpdate, f.lastCheck,
            f.lastCheckError, f.refreshInterval,
            COUNT(fi.itemID) AS total_count,
            COALESCE(SUM(CASE WHEN fi.readTime IS NULL
                AND fi.itemID IS NOT NULL THEN 1 ELSE 0 END), 0) AS unread_count
        FROM feeds f
        LEFT JOIN items i ON i.libraryID = f.libraryID
        LEFT JOIN feedItems fi ON fi.itemID = i.itemID
        GROUP BY f.libraryID
        ORDER BY f.name
        """
        cur = self._conn.execute(sql)
        return [dict(r) for r in cur.fetchall()]

    def feed_exists(self, feed_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM feeds WHERE libraryID = ?", (feed_id,)
        )
        return cur.fetchone() is not None

    def query_items(
        self,
        feed_id: int,
        *,
        date_start: str = "0000-00-00",
        date_end: str = "9999-12-31",
        include_undated: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        fid_title = self._field_id("title")
        fid_date = self._field_id("date")
        fid_url = self._field_id("url")
        fid_abstract = self._field_id("abstractNote")

        sql = """
        SELECT
            fi.itemID AS item_id, fi.guid, fi.readTime AS read_time,
            fi.translatedTime AS translated_time,
            COALESCE(title_v.value, '') AS title,
            COALESCE(date_v.value, '') AS date_raw,
            SUBSTR(COALESCE(date_v.value, ''), 1, 10) AS date_sql,
            COALESCE(url_v.value, '') AS url,
            COALESCE(abstract_v.value, '') AS abstract
        FROM feedItems fi
        JOIN items i ON i.itemID = fi.itemID
        LEFT JOIN itemData title_id ON title_id.itemID = i.itemID
            AND title_id.fieldID = ?
        LEFT JOIN itemDataValues title_v ON title_v.valueID = title_id.valueID
        LEFT JOIN itemData date_id ON date_id.itemID = i.itemID
            AND date_id.fieldID = ?
        LEFT JOIN itemDataValues date_v ON date_v.valueID = date_id.valueID
        LEFT JOIN itemData url_id ON url_id.itemID = i.itemID
            AND url_id.fieldID = ?
        LEFT JOIN itemDataValues url_v ON url_v.valueID = url_id.valueID
        LEFT JOIN itemData abstract_id ON abstract_id.itemID = i.itemID
            AND abstract_id.fieldID = ?
        LEFT JOIN itemDataValues abstract_v ON abstract_v.valueID = abstract_id.valueID
        WHERE i.libraryID = ?
          AND (
            (? = 1 AND date_v.value IS NULL)
            OR (
              date_v.value IS NOT NULL
              AND SUBSTR(date_v.value, 1, 10) >= ?
              AND SUBSTR(date_v.value, 1, 10) <= ?
            )
          )
        ORDER BY SUBSTR(date_v.value, 1, 10) DESC NULLS LAST
        LIMIT ?
        """
        params = (
            fid_title, fid_date, fid_url, fid_abstract,
            feed_id,
            1 if include_undated else 0,
            date_start, date_end,
            limit,
        )
        cur = self._conn.execute(sql, params)
        result = []
        for r in cur.fetchall():
            d = dict(r)
            d["feed_id"] = feed_id
            result.append(d)
        return result

    def query_creators(self, item_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not item_ids:
            return {}
        placeholders = ",".join("?" * len(item_ids))
        sql = f"""
        SELECT ic.itemID, c.firstName, c.lastName, c.fieldMode,
               ct.creatorType, ic.orderIndex
        FROM itemCreators ic
        JOIN creators c ON c.creatorID = ic.creatorID
        JOIN creatorTypes ct ON ct.creatorTypeID = ic.creatorTypeID
        WHERE ic.itemID IN ({placeholders})
        ORDER BY ic.itemID, ic.orderIndex
        """
        cur = self._conn.execute(sql, tuple(item_ids))
        result: dict[int, list[dict[str, Any]]] = {}
        for r in cur.fetchall():
            d = dict(r)
            iid = d.pop("itemID")
            result.setdefault(iid, []).append(d)
        return result

    def close(self) -> None:
        self._conn.close()
