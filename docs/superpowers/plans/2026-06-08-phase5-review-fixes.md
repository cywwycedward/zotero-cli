# Phase 5 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 6 review findings (3 P1 + 3 P2) so Phase 5 can pass acceptance.

**Architecture:** Surgical fixes only — each finding maps to 1–2 files. No structural changes. Test-first for every bug fix per DEVELOPMENT.md §6.1.

**Tech Stack:** Python 3.11, Pydantic, sqlite3, pytest, Typer

---

## File Map

| Finding | Files to modify | Test files |
|---------|----------------|------------|
| F1: --quiet crash | `src/zotero_cli/commands/feeds.py` | `tests/unit/test_feed_commands.py` (create) |
| F2: SQLite error translation | `src/zotero_cli/adapters/sqlite_reader.py` | `tests/unit/test_sqlite_reader.py` (create) |
| F3: FEED_NOT_FOUND | `src/zotero_cli/commands/feeds.py` | `tests/unit/test_feed_commands.py` |
| F4: date field missing | `src/zotero_cli/models/config.py` | `tests/unit/test_feed_commands.py` |
| F5: empty feed unread_count | `src/zotero_cli/adapters/sqlite_reader.py` | `tests/integration/test_feed_queries.py` |
| F6: deliverables | `tests/integration/test_feed_perf.py` (create), `tests/fixtures/build_sqlite.py` | — |

---

### Task 1: F1 — Fix --quiet crash (model_dump() missing "key")

**Root cause:** `_render_quiet()` in `output.py:227` does `item["key"]` on list items. The feed commands pass `model_dump()` dicts, but `FeedItem.key` and `FeedSummary` lack a `key` field — `key` is a `@property` on `FeedItem` only, excluded from `model_dump()`.

**Fix approach:** Include `key` in `model_dump()` output for both models. Pydantic v2 `@computed_field` makes a `@property` appear in `model_dump()`. Add `@computed_field` + `@property` on both `FeedSummary` (using `str(feed_id)`) and `FeedItem` (already has `key` property, just needs decorator).

**Files:**
- Modify: `src/zotero_cli/models/feed.py:7-19` (FeedSummary) and `feed.py:48-51` (FeedItem.key)
- Test: `tests/unit/test_feed_commands.py` (create)

- [ ] **Step 1: Write failing tests for --quiet on both feed models**

Create `tests/unit/test_feed_commands.py`:

```python
"""Unit tests for feed commands — focuses on --quiet, error paths, field filter."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zotero_cli.models.feed import FeedItem, FeedSummary


class TestFeedModelKeys:
    """F1: model_dump() must include 'key' for --quiet rendering."""

    def test_feed_summary_dump_contains_key(self) -> None:
        summary = FeedSummary(
            feed_id=10, name="Test", url="https://example.com",
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_feed_commands.py::TestFeedModelKeys -v`
Expected: 2 FAILED — `"key" not in d`

- [ ] **Step 3: Add @computed_field to both models**

Edit `src/zotero_cli/models/feed.py`:

```python
"""Feed models for RSS query results (design §11.2)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field


class FeedSummary(BaseModel):
    """A single feed subscription (feeds list)."""
    model_config = ConfigDict(extra="forbid")

    feed_id: int = Field(alias="libraryID")
    name: str
    url: str
    last_update: str | None = Field(default=None, alias="lastUpdate")
    last_check: str | None = Field(default=None, alias="lastCheck")
    last_check_error: str | None = Field(default=None, alias="lastCheckError")
    refresh_interval: int = Field(default=0, alias="refreshInterval")
    total_count: int = 0
    unread_count: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        """Used by --quiet output."""
        return str(self.feed_id)


class FeedItemCreator(BaseModel):
    """A single creator for a feed item."""
    model_config = ConfigDict(extra="forbid")

    first_name: str = ""
    last_name: str = ""
    creator_type: str = ""
    order_index: int = 0


class FeedItem(BaseModel):
    """A single feed item (feeds items query)."""
    model_config = ConfigDict(extra="forbid")

    feed_id: int
    item_id: int
    guid: str = ""
    title: str = ""
    date_raw: str = ""
    date_sql: str = ""
    url: str = ""
    abstract: str = ""
    read_time: str | None = None
    translated_time: str | None = None
    creators: list[FeedItemCreator] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        """Used by --quiet output."""
        return str(self.item_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_feed_commands.py::TestFeedModelKeys -v`
Expected: 2 PASSED

- [ ] **Step 5: Verify existing integration tests still pass**

Run: `uv run pytest tests/integration/test_feed_queries.py -v`
Expected: 8 PASSED (no regression)

- [ ] **Step 6: Commit**

```bash
git add src/zotero_cli/models/feed.py tests/unit/test_feed_commands.py
git commit -m "$(cat <<'EOF'
fix(feed): add computed_field key to FeedSummary/FeedItem for --quiet rendering

model_dump() excluded @property fields, causing KeyError in _render_quiet().
Use Pydantic @computed_field so 'key' appears in dump output.
EOF
)"
```

---

### Task 2: F2 — SQLite error translation + schema column checks

**Root cause:** `sqlite3.connect()` at `sqlite_reader.py:24` doesn't catch `sqlite3.OperationalError` when the file is missing. Schema check (`_check_schema`) only verifies table names, not required columns (`feedItems.guid`, `feedItems.readTime`, `feedItems.translatedTime`).

**Fix approach:**
1. Wrap `sqlite3.connect()` in try/except → raise `SqliteNotFoundError` with exit code 4.
2. After table check, add a column existence check for the `feedItems` columns that `query_items` relies on.

**Files:**
- Modify: `src/zotero_cli/adapters/sqlite_reader.py:23-41`
- Test: `tests/unit/test_sqlite_reader.py` (create)

- [ ] **Step 1: Write failing tests for SQLite error translation**

Create `tests/unit/test_sqlite_reader.py`:

```python
"""Unit tests for SQLiteReader — error paths and schema validation."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from zotero_cli.adapters.sqlite_reader import SQLiteReader
from zotero_cli.models.config import SQLiteConfig
from zotero_cli.models.errors import SqliteNotFoundError, SqliteSchemaIncompatibleError


class TestSqliteConnectionErrors:
    """F2: sqlite3 exceptions must be translated to CLIError subclasses."""

    def test_missing_file_raises_sqlite_not_found(self, tmp_path: Path) -> None:
        config = SQLiteConfig(path=str(tmp_path / "nonexistent.sqlite"))
        with pytest.raises(SqliteNotFoundError) as exc_info:
            SQLiteReader(config)
        assert exc_info.value.exit_code == 4

    def test_none_path_raises_sqlite_not_found(self) -> None:
        config = SQLiteConfig(path=None)
        with pytest.raises(SqliteNotFoundError):
            SQLiteReader(config)


class TestSchemaValidation:
    """F2: schema check must verify required columns, not just table names."""

    def test_missing_table_raises_schema_incompatible(self, tmp_path: Path) -> None:
        db_path = tmp_path / "bad.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE feeds(libraryID INTEGER)")
        conn.close()
        config = SQLiteConfig(path=str(db_path))
        with pytest.raises(SqliteSchemaIncompatibleError):
            SQLiteReader(config)

    def test_missing_feeditems_columns_raises_schema_incompatible(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "partial.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE items(itemID INTEGER PRIMARY KEY);
            CREATE TABLE feedItems(itemID INTEGER PRIMARY KEY);
            CREATE TABLE feeds(libraryID INTEGER PRIMARY KEY);
            CREATE TABLE fields(fieldID INTEGER PRIMARY KEY, fieldName TEXT);
            CREATE TABLE itemData(itemID INTEGER, fieldID INTEGER, valueID INTEGER);
            CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY, value TEXT);
        """)
        conn.close()
        config = SQLiteConfig(path=str(db_path))
        with pytest.raises(SqliteSchemaIncompatibleError, match="guid"):
            SQLiteReader(config)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sqlite_reader.py -v`
Expected: `test_missing_file_raises_sqlite_not_found` FAILED (gets `sqlite3.OperationalError` instead); `test_missing_feeditems_columns_raises_schema_incompatible` FAILED (no column check)

- [ ] **Step 3: Implement SQLite error translation and column check**

Edit `src/zotero_cli/adapters/sqlite_reader.py` — replace the `__init__` and `_check_schema` methods:

```python
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
        """Verify required tables and columns exist."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sqlite_reader.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All pass (integration tests still use valid fixture)

- [ ] **Step 6: Commit**

```bash
git add src/zotero_cli/adapters/sqlite_reader.py tests/unit/test_sqlite_reader.py
git commit -m "$(cat <<'EOF'
fix(sqlite_reader): translate sqlite3 errors to CLIError + validate feedItems columns

sqlite3.OperationalError on missing file now raises SqliteNotFoundError (exit 4).
Schema check now verifies feedItems.guid/readTime/translatedTime columns exist.
EOF
)"
```

---

### Task 3: F3 — feeds items <unknown-id> returns FEED_NOT_FOUND

**Root cause:** `feeds items` command at `feeds.py:96` calls `svc.list_items(feed_id)` directly without checking if the feed exists. Returns empty list + exit 0 for non-existent feeds.

**Fix approach:** Add a `feed_exists(feed_id)` check in `FeedService.list_items()` before querying items. Raise `FeedNotFoundError` if the feed doesn't exist. This follows the same pattern as `feeds show` but at the service layer (reusable).

**Files:**
- Modify: `src/zotero_cli/services/feed_service.py:19-26`
- Modify: `src/zotero_cli/adapters/sqlite_reader.py` (add `feed_exists` method)
- Test: `tests/unit/test_feed_commands.py` (add test), `tests/integration/test_feed_queries.py` (add test)

- [ ] **Step 1: Write failing test for unknown feed_id**

Add to `tests/unit/test_feed_commands.py`:

```python
from zotero_cli.models.errors import FeedNotFoundError
from zotero_cli.services.feed_service import FeedService


class TestFeedNotFound:
    """F3: feeds items <unknown-id> must raise FEED_NOT_FOUND."""

    def test_list_items_unknown_feed_raises(self) -> None:
        mock_reader = MagicMock()
        mock_reader.feed_exists.return_value = False
        svc = FeedService(mock_reader)
        with pytest.raises(FeedNotFoundError):
            svc.list_items(99999)
```

Add to `tests/integration/test_feed_queries.py`:

```python
from zotero_cli.models.errors import FeedNotFoundError


class TestFeedNotFoundIntegration:
    def test_list_items_unknown_feed_raises(self, svc: FeedService) -> None:
        with pytest.raises(FeedNotFoundError):
            svc.list_items(99999)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_feed_commands.py::TestFeedNotFound -v`
Expected: FAILED — no `feed_exists` method / no error raised

- [ ] **Step 3: Add feed_exists to SQLiteReader**

Add to `src/zotero_cli/adapters/sqlite_reader.py` (after `list_feeds` method):

```python
    def feed_exists(self, feed_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM feeds WHERE libraryID = ?", (feed_id,)
        )
        return cur.fetchone() is not None
```

- [ ] **Step 4: Add existence check to FeedService.list_items**

Edit `src/zotero_cli/services/feed_service.py` — add import and check at start of `list_items`:

```python
from zotero_cli.models.errors import FeedNotFoundError

# ... inside list_items, before date processing:
        if not self._reader.feed_exists(feed_id):
            raise FeedNotFoundError(
                f"Feed {feed_id} not found",
                hint="Use 'feeds list' to see available feeds.",
            )
```

- [ ] **Step 5: Simplify feeds show to use feed_exists too**

Edit `src/zotero_cli/commands/feeds.py` — replace the `show_feed` work function to use the service-layer check, removing the inline search:

```python
@app.command("show")
def show_feed(
    ctx: typer.Context,
    feed_id: Annotated[int, typer.Argument(help="Feed libraryID")],
) -> None:
    """Show details of a single feed."""
    def work() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        feeds = svc.list_feeds()
        match = next((f for f in feeds if f.feed_id == feed_id), None)
        if match is None:
            from zotero_cli.models.errors import FeedNotFoundError
            raise FeedNotFoundError(f"Feed {feed_id} not found")
        return match.model_dump(), None

    _invoke(ctx, "feeds.show", OutputMode.KV, work)
```

(No change to `show_feed` — the inline check is fine for show since it already works correctly. Keep it simple.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_feed_commands.py::TestFeedNotFound tests/integration/test_feed_queries.py::TestFeedNotFoundIntegration -v`
Expected: 2 PASSED

- [ ] **Step 7: Run full integration tests**

Run: `uv run pytest tests/integration/test_feed_queries.py -v`
Expected: All pass (existing tests use valid feed_id=10)

- [ ] **Step 8: Commit**

```bash
git add src/zotero_cli/adapters/sqlite_reader.py src/zotero_cli/services/feed_service.py tests/unit/test_feed_commands.py tests/integration/test_feed_queries.py
git commit -m "$(cat <<'EOF'
fix(feed_service): raise FEED_NOT_FOUND for unknown feed_id in list_items

feeds items <unknown-id> previously returned exit 0 with empty output.
Now raises FeedNotFoundError (exit 1) via feed_exists() check in service layer.
EOF
)"
```

---

### Task 4: F4 — Default feeds items output missing "date" field

**Root cause:** Default `feed_item_fields.list` in `config.py:31` includes `"date"`, but `FeedItem.model_dump()` only has `date_raw` and `date_sql` — no field named `date`. After field filtering, the date column is silently dropped.

**Fix approach:** Add a `date` computed field to `FeedItem` that returns `date_raw` (the human-readable date string from Zotero). This matches what users expect and aligns the model with the config default. The `date_raw` / `date_sql` fields remain for programmatic access.

**Files:**
- Modify: `src/zotero_cli/models/feed.py` (add `date` computed field)
- Test: `tests/unit/test_feed_commands.py` (add test)

- [ ] **Step 1: Write failing test for date in model_dump**

Add to `tests/unit/test_feed_commands.py` under `TestFeedModelKeys`:

```python
    def test_feed_item_dump_contains_date(self) -> None:
        item = FeedItem(feed_id=10, item_id=1001, date_raw="2024-06-15 2024-06-15")
        d = item.model_dump()
        assert "date" in d
        assert d["date"] == "2024-06-15 2024-06-15"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_feed_commands.py::TestFeedModelKeys::test_feed_item_dump_contains_date -v`
Expected: FAILED — `"date" not in d`

- [ ] **Step 3: Add date computed field to FeedItem**

Edit `src/zotero_cli/models/feed.py` — add to `FeedItem` class, after `creators`:

```python
    @computed_field  # type: ignore[prop-decorator]
    @property
    def date(self) -> str:
        return self.date_raw
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_feed_commands.py::TestFeedModelKeys -v`
Expected: 3 PASSED

- [ ] **Step 5: Verify integration tests**

Run: `uv run pytest tests/integration/test_feed_queries.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/zotero_cli/models/feed.py tests/unit/test_feed_commands.py
git commit -m "$(cat <<'EOF'
fix(feed): add computed 'date' field to FeedItem for default field filter

Default feed_item_fields config includes 'date' but model_dump() only
had date_raw/date_sql. Add computed 'date' property aliasing date_raw.
EOF
)"
```

---

### Task 5: F5 — Empty feed unread_count counts as 1

**Root cause:** SQL at `sqlite_reader.py:59`:
```sql
SUM(CASE WHEN fi.readTime IS NULL THEN 1 ELSE 0 END) AS unread_count
```
When a feed has zero items, `LEFT JOIN` produces one row with all-NULL values. `fi.readTime IS NULL` evaluates to `TRUE` on that row, so `SUM(...)` = 1.

**Fix approach:** Use `COALESCE(SUM(CASE WHEN fi.readTime IS NULL AND fi.itemID IS NOT NULL THEN 1 ELSE 0 END), 0)` — the `fi.itemID IS NOT NULL` guard excludes the phantom LEFT JOIN row.

**Files:**
- Modify: `src/zotero_cli/adapters/sqlite_reader.py:59-60`
- Modify: `tests/fixtures/build_sqlite.py` (add empty feed)
- Test: `tests/integration/test_feed_queries.py` (add test)

- [ ] **Step 1: Add empty feed to test fixture**

Edit `tests/fixtures/build_sqlite.py` — add a second feed with no items, after the existing feed insert:

```python
    # Empty feed (for unread_count=0 test)
    db.execute("INSERT INTO libraries VALUES(20, 'feed')")
    db.execute("""
        INSERT INTO feeds VALUES(20, 'Empty Feed', 'https://example.com/empty',
            '2024-06-20 10:00:00', '2024-06-20 10:00:00', NULL, 60)
    """)
```

- [ ] **Step 2: Rebuild the fixture**

Run: `uv run python tests/fixtures/build_sqlite.py`
Expected: `Created tests/fixtures/zotero_test.sqlite`

- [ ] **Step 3: Write failing test for empty feed unread_count**

Add to `tests/integration/test_feed_queries.py`:

```python
class TestEmptyFeed:
    """F5: empty feed must have unread_count=0, not 1."""

    def test_empty_feed_unread_count_zero(self, svc: FeedService) -> None:
        feeds = svc.list_feeds()
        empty = next(f for f in feeds if f.name == "Empty Feed")
        assert empty.total_count == 0
        assert empty.unread_count == 0
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_feed_queries.py::TestEmptyFeed -v`
Expected: FAILED — `assert 1 == 0` (unread_count is 1)

- [ ] **Step 5: Fix the SQL**

Edit `src/zotero_cli/adapters/sqlite_reader.py` — replace line 60:

Old:
```python
            SUM(CASE WHEN fi.readTime IS NULL THEN 1 ELSE 0 END) AS unread_count
```

New:
```python
            COALESCE(SUM(CASE WHEN fi.readTime IS NULL AND fi.itemID IS NOT NULL THEN 1 ELSE 0 END), 0) AS unread_count
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_feed_queries.py -v`
Expected: All pass including new TestEmptyFeed

- [ ] **Step 7: Update TestFeedList.test_lists_feeds for 2 feeds**

The existing test asserts `len(feeds) == 1`. Update to `len(feeds) == 2` and keep the assertion on the first feed's data:

```python
    def test_lists_feeds(self, svc: FeedService) -> None:
        feeds = svc.list_feeds()
        assert len(feeds) == 2
        test_feed = next(f for f in feeds if f.name == "Test Feed")
        assert test_feed.total_count == 5
```

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest tests/ --tb=short`
Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add src/zotero_cli/adapters/sqlite_reader.py tests/fixtures/build_sqlite.py tests/fixtures/zotero_test.sqlite tests/integration/test_feed_queries.py
git commit -m "$(cat <<'EOF'
fix(sqlite_reader): empty feed unread_count was 1, should be 0

LEFT JOIN phantom row caused SUM(CASE WHEN readTime IS NULL) to count 1.
Add fi.itemID IS NOT NULL guard to exclude phantom rows.
EOF
)"
```

---

### Task 6: F6a — Add performance test (test_feed_perf.py)

**Root cause:** DEVELOPMENT.md §9.5 requires: "性能测试：1000 条 feed items + date 过滤 < 300ms". No `test_feed_perf.py` exists.

**Files:**
- Modify: `tests/fixtures/build_sqlite.py` (add `build_with_n_items` function)
- Create: `tests/integration/test_feed_perf.py`

- [ ] **Step 1: Add build_with_n_items to build_sqlite.py**

Edit `tests/fixtures/build_sqlite.py` — add a reusable function after the `if __name__` block's content:

```python
def build_with_n_items(path: Path, n: int = 1000) -> None:
    """Build a fixture with a single feed containing n items, for perf tests."""
    path.unlink(missing_ok=True)
    db = sqlite3.connect(str(path))
    db.execute("BEGIN")

    db.executescript("""
    CREATE TABLE libraries(libraryID INTEGER PRIMARY KEY, type TEXT);
    CREATE TABLE feeds(
        libraryID INTEGER PRIMARY KEY, name TEXT, url TEXT,
        lastUpdate TEXT, lastCheck TEXT, lastCheckError TEXT, refreshInterval INTEGER,
        FOREIGN KEY(libraryID) REFERENCES libraries(libraryID)
    );
    CREATE TABLE items(itemID INTEGER PRIMARY KEY, libraryID INTEGER,
                       dateAdded TEXT, dateModified TEXT);
    CREATE TABLE feedItems(
        itemID INTEGER PRIMARY KEY, guid TEXT UNIQUE,
        readTime TEXT, translatedTime TEXT,
        FOREIGN KEY(itemID) REFERENCES items(itemID)
    );
    CREATE TABLE fields(fieldID INTEGER PRIMARY KEY, fieldName TEXT);
    CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY, value TEXT);
    CREATE TABLE itemData(itemID INTEGER, fieldID INTEGER, valueID INTEGER,
                          PRIMARY KEY(itemID, fieldID));
    CREATE TABLE creators(creatorID INTEGER PRIMARY KEY, firstName TEXT,
                          lastName TEXT, fieldMode INTEGER);
    CREATE TABLE creatorTypes(creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
    CREATE TABLE itemCreators(itemID INTEGER, creatorID INTEGER,
                              creatorTypeID INTEGER, orderIndex INTEGER,
                              PRIMARY KEY(itemID, creatorID, orderIndex));
    """)

    db.execute("INSERT INTO libraries VALUES(1, 'feed')")
    db.execute("""
        INSERT INTO feeds VALUES(1, 'Perf Feed', 'https://example.com/perf',
            '2024-01-01', '2024-01-01', NULL, 60)
    """)
    for fid, fname in [(1, "title"), (2, "abstractNote"), (13, "url"), (14, "date")]:
        db.execute("INSERT INTO fields VALUES(?, ?)", (fid, fname))
    db.execute("INSERT INTO creatorTypes VALUES(1, 'author')")

    vid = 0
    for i in range(1, n + 1):
        month = ((i - 1) % 12) + 1
        day = ((i - 1) % 28) + 1
        date_str = f"2024-{month:02d}-{day:02d}"
        db.execute("INSERT INTO items VALUES(?, 1, ?, ?)", (i, date_str, date_str))
        db.execute(
            "INSERT INTO feedItems VALUES(?, ?, NULL, NULL)",
            (i, f"guid-{i}"),
        )
        vid += 1
        db.execute("INSERT INTO itemDataValues VALUES(?, ?)", (vid, f"Title {i}"))
        db.execute("INSERT INTO itemData VALUES(?, 1, ?)", (i, vid))
        vid += 1
        db.execute("INSERT INTO itemDataValues VALUES(?, ?)", (vid, date_str))
        db.execute("INSERT INTO itemData VALUES(?, 14, ?)", (i, vid))

    db.commit()
    db.close()
```

- [ ] **Step 2: Create test_feed_perf.py**

Create `tests/integration/test_feed_perf.py`:

```python
"""Performance test: 1000 feed items + date filter < 300ms (DEVELOPMENT.md §9.5)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from zotero_cli.adapters.sqlite_reader import SQLiteReader
from zotero_cli.models.config import SQLiteConfig
from zotero_cli.services.feed_service import FeedService
from tests.fixtures.build_sqlite import build_with_n_items

PERF_DB = Path(__file__).parent.parent / "fixtures" / "perf_test.sqlite"


@pytest.fixture(scope="module")
def perf_svc() -> FeedService:
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
```

- [ ] **Step 3: Run perf tests**

Run: `uv run pytest tests/integration/test_feed_perf.py -v`
Expected: 2 PASSED, each < 300ms

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/build_sqlite.py tests/integration/test_feed_perf.py
git commit -m "$(cat <<'EOF'
test(feed): add performance test — 1000 items + date filter < 300ms

Adds build_with_n_items() to build_sqlite.py and test_feed_perf.py
per DEVELOPMENT.md §9.5 acceptance criteria.
EOF
)"
```

---

### Task 7: F6b — Raise commands/feeds.py coverage to ≥ 70%

**Root cause:** `commands/feeds.py` coverage is 30%. Most command functions are untested because they require mocking the full Typer + runner stack.

**Fix approach:** Add CLI-level unit tests using Typer's `CliRunner` + mock `FeedService` to exercise all 3 command paths (list, show, items) including error paths. This covers the `_invoke` / `_get_svc` / work-function code paths.

**Files:**
- Test: `tests/unit/test_feed_commands.py` (extend)

- [ ] **Step 1: Write CLI-level tests**

Add to `tests/unit/test_feed_commands.py`:

```python
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from zotero_cli.commands.feeds import app as feeds_app
from zotero_cli.commands._runner import GlobalOptions
from zotero_cli.models.feed import FeedSummary, FeedItem
from zotero_cli.models.errors import FeedNotFoundError


runner = CliRunner()


def _make_ctx_obj(**overrides: Any) -> GlobalOptions:
    defaults = {"profile": "default", "json_mode": False, "quiet": False, "config_path": None}
    defaults.update(overrides)
    return GlobalOptions(**defaults)


class TestFeedsListCommand:
    """CLI-level tests for 'feeds list'."""

    @patch("zotero_cli.commands.feeds._get_svc")
    def test_list_feeds_success(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = [
            FeedSummary(feed_id=10, name="Test", url="https://example.com",
                        total_count=5, unread_count=3),
        ]
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["list"], obj=_make_ctx_obj())
        assert result.exit_code == 0
        assert "Test" in result.stdout

    @patch("zotero_cli.commands.feeds._get_svc")
    def test_list_feeds_quiet(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = [
            FeedSummary(feed_id=10, name="Test", url="https://example.com",
                        total_count=5, unread_count=3),
        ]
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["list"], obj=_make_ctx_obj(quiet=True))
        assert result.exit_code == 0
        assert "10" in result.stdout


class TestFeedsShowCommand:
    @patch("zotero_cli.commands.feeds._get_svc")
    def test_show_feed_success(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = [
            FeedSummary(feed_id=10, name="Test", url="https://example.com",
                        total_count=5, unread_count=3),
        ]
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["show", "10"], obj=_make_ctx_obj())
        assert result.exit_code == 0

    @patch("zotero_cli.commands.feeds._get_svc")
    def test_show_feed_not_found(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.list_feeds.return_value = []
        mock_get_svc.return_value = mock_svc
        result = runner.invoke(feeds_app, ["show", "99"], obj=_make_ctx_obj())
        assert result.exit_code == 1


class TestFeedsItemsCommand:
    @patch("zotero_cli.commands.feeds.load_config")
    @patch("zotero_cli.commands.feeds.SQLiteReader")
    @patch("zotero_cli.commands.feeds.FeedService")
    def test_items_success(
        self, mock_svc_cls: MagicMock, mock_reader_cls: MagicMock,
        mock_load_config: MagicMock,
    ) -> None:
        mock_profile = MagicMock()
        mock_profile.feed_item_fields.list = ["title", "url"]
        mock_profile.sqlite = MagicMock()
        mock_load_config.return_value = mock_profile
        mock_svc = MagicMock()
        mock_svc.list_items.return_value = [
            FeedItem(feed_id=10, item_id=1001, title="Article"),
        ]
        mock_svc_cls.return_value = mock_svc
        result = runner.invoke(feeds_app, ["items", "10"], obj=_make_ctx_obj())
        assert result.exit_code == 0

    @patch("zotero_cli.commands.feeds.load_config")
    @patch("zotero_cli.commands.feeds.SQLiteReader")
    @patch("zotero_cli.commands.feeds.FeedService")
    def test_items_not_found(
        self, mock_svc_cls: MagicMock, mock_reader_cls: MagicMock,
        mock_load_config: MagicMock,
    ) -> None:
        mock_profile = MagicMock()
        mock_profile.feed_item_fields.list = ["title"]
        mock_profile.sqlite = MagicMock()
        mock_load_config.return_value = mock_profile
        mock_svc = MagicMock()
        mock_svc.list_items.side_effect = FeedNotFoundError("Feed 99 not found")
        mock_svc_cls.return_value = mock_svc
        result = runner.invoke(feeds_app, ["items", "99"], obj=_make_ctx_obj())
        assert result.exit_code == 1
```

- [ ] **Step 2: Run tests and check coverage**

Run: `uv run pytest tests/unit/test_feed_commands.py -v`
Expected: All PASSED

Run: `uv run pytest --cov=zotero_cli.commands.feeds --cov-report=term-missing tests/`
Expected: commands/feeds.py coverage ≥ 70%

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_feed_commands.py
git commit -m "$(cat <<'EOF'
test(feeds): add CLI-level unit tests — coverage from 30% to ≥70%

Tests list/show/items commands via CliRunner with mocked service,
covering success paths, --quiet, and error paths.
EOF
)"
```

---

### Task 8: Self-check and mark §9.5 complete

- [ ] **Step 1: Run full self-check battery**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src --cov-report=term-missing
```

All four must pass.

- [ ] **Step 2: Verify per-module coverage targets**

```bash
uv run pytest --cov=zotero_cli.commands.feeds --cov=zotero_cli.adapters.sqlite_reader --cov=zotero_cli.services.feed_service --cov-report=term-missing tests/
```

Expected: `commands/feeds.py` ≥ 70%, `adapters/sqlite_reader.py` ≥ 90%, `services/feed_service.py` ≥ 85%

- [ ] **Step 3: Check DEVELOPMENT.md §9.5 items**

Manually verify each checkbox in §9.5 is now satisfied, then update to `[x]`.

- [ ] **Step 4: Final commit**

```bash
git add DEVELOPMENT.md
git commit -m "$(cat <<'EOF'
docs(phase5): mark §9.5 acceptance criteria complete
EOF
)"
```

---

## Summary of Changes Per File

| File | Changes |
|------|---------|
| `src/zotero_cli/models/feed.py` | Add `@computed_field` to `FeedSummary.key`, `FeedItem.key`, `FeedItem.date` |
| `src/zotero_cli/adapters/sqlite_reader.py` | Wrap `connect()` in try/except, add column check in `_check_schema`, add `feed_exists()`, fix unread_count SQL |
| `src/zotero_cli/services/feed_service.py` | Add `feed_exists` guard in `list_items` |
| `tests/fixtures/build_sqlite.py` | Add empty feed to fixture, add `build_with_n_items()` |
| `tests/unit/test_feed_commands.py` | New: model key tests, CLI-level tests |
| `tests/unit/test_sqlite_reader.py` | New: error translation + schema validation tests |
| `tests/integration/test_feed_queries.py` | Add empty feed test, feed-not-found test |
| `tests/integration/test_feed_perf.py` | New: 1000-item performance test |
| `DEVELOPMENT.md` | Check off §9.5 items |
