"""Build a minimal zotero_test.sqlite for RSS feed tests (design §12.3).

Usage: uv run python tests/fixtures/build_sqlite.py
Output: tests/fixtures/zotero_test.sqlite (overwritten)
"""
import sqlite3
from pathlib import Path

OUT = Path(__file__).parent / "zotero_test.sqlite"


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


if __name__ == "__main__":
    OUT.unlink(missing_ok=True)
    db = sqlite3.connect(str(OUT))
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

    # libraries
    db.execute("INSERT INTO libraries VALUES(10, 'feed')")

    # feeds
    db.execute("""
        INSERT INTO feeds VALUES(10, 'Test Feed', 'https://example.com/rss',
            '2024-06-20 10:00:00', '2024-06-20 10:00:00', NULL, 60)
    """)

    # fields: title=1, abstractNote=2, url=13, date=14
    for fid, fname in [(1, "title"), (2, "abstractNote"), (13, "url"), (14, "date")]:
        db.execute("INSERT INTO fields VALUES(?, ?)", (fid, fname))

    # creatorTypes
    db.execute("INSERT INTO creatorTypes VALUES(1, 'author')")

    items = [
        (1001, 10, "2024-06-15", "2024-06-15"),
        (1002, 10, "2024-06-01", "2024-06-01"),
        (1003, 10, "2024-01-01", "2024-01-01"),
        (1004, 10, "2023-12-31", "2023-12-31"),
        (1005, 10, "2024-01-01", "2024-01-01"),
    ]
    db.executemany("INSERT INTO items VALUES(?, ?, ?, ?)", items)

    feed_items = [
        (1001, "feed1-guid-1001", None, None),
        (1002, "feed1-guid-1002", "2024-07-01 09:00:00", "2024-07-01 09:00:00"),
        (1003, "feed1-guid-1003", None, None),
        (1004, "feed1-guid-1004", "2024-01-05 00:00:00", "2024-01-05 00:00:00"),
        (1005, "feed1-guid-1005", None, None),
    ]
    db.executemany("INSERT INTO feedItems VALUES(?, ?, ?, ?)", feed_items)

    # itemDataValues + itemData
    def _add_data(item_id: int, field_id: int, value: str, vid: int) -> None:
        db.execute("INSERT INTO itemDataValues VALUES(?, ?)", (vid, value))
        db.execute("INSERT INTO itemData VALUES(?, ?, ?)", (item_id, field_id, vid))

    # 1001: Full Date Item — title, date, url, abstract, 1 creator
    _add_data(1001, 1, "Full Date Item", 1)
    _add_data(1001, 14, "2024-06-15 2024-06-15", 2)
    _add_data(1001, 13, "https://example.com/full", 3)
    _add_data(1001, 2, "Abstract for full date", 4)
    # 1002: Year-Month Item — title, date, url, 2 creators
    _add_data(1002, 1, "Year-Month Item", 5)
    _add_data(1002, 14, "2024-06-00 June 2024", 6)
    _add_data(1002, 13, "https://example.com/ym", 7)
    # 1003: Year-Only Item — title, date, abstract
    _add_data(1003, 1, "Year-Only Item", 8)
    _add_data(1003, 14, "2024-00-00 2024", 9)
    _add_data(1003, 2, "Abstract for year only", 10)
    # 1004: Out-of-Range Item — all fields
    _add_data(1004, 1, "Out-of-Range Item", 11)
    _add_data(1004, 14, "2023-12-31 2023-12-31", 12)
    _add_data(1004, 13, "https://example.com/out", 13)
    _add_data(1004, 2, "Abstract out of range", 14)
    # 1005: Undated Item — only title (no date row)
    _add_data(1005, 1, "Undated Item", 15)

    # creators
    db.execute("INSERT INTO creators VALUES(1, 'John', 'Doe', 0)")
    db.execute("INSERT INTO creators VALUES(2, 'Jane', 'Smith', 0)")
    # itemCreators: 1001 has creator 1, 1002 has both
    db.execute("INSERT INTO itemCreators VALUES(1001, 1, 1, 0)")
    db.execute("INSERT INTO itemCreators VALUES(1002, 1, 1, 0)")
    db.execute("INSERT INTO itemCreators VALUES(1002, 2, 1, 1)")

    # Empty feed (for unread_count=0 test)
    db.execute("INSERT INTO libraries VALUES(20, 'feed')")
    db.execute("""
        INSERT INTO feeds VALUES(20, 'Empty Feed', 'https://example.com/empty',
            '2024-06-20 10:00:00', '2024-06-20 10:00:00', NULL, 60)
    """)

    db.commit()
    db.close()
    print(f"Created {OUT}")
