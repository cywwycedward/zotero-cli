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

    def test_missing_feeditems_columns_raises_schema_incompatible(self, tmp_path: Path) -> None:
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


class TestQueryItemData:
    """Tests for SQLiteReader.query_item_data()."""

    @pytest.fixture()
    def reader(self, tmp_path: Path):
        db_path = tmp_path / "test.sqlite"
        db = sqlite3.connect(str(db_path))
        db.executescript("""
        CREATE TABLE libraries(libraryID INTEGER PRIMARY KEY, type TEXT);
        CREATE TABLE feeds(
            libraryID INTEGER PRIMARY KEY, name TEXT, url TEXT,
            lastUpdate TEXT, lastCheck TEXT, lastCheckError TEXT,
            refreshInterval INTEGER
        );
        CREATE TABLE items(itemID INTEGER PRIMARY KEY, libraryID INTEGER,
                           dateAdded TEXT, dateModified TEXT);
        CREATE TABLE feedItems(
            itemID INTEGER PRIMARY KEY, guid TEXT UNIQUE,
            readTime TEXT, translatedTime TEXT
        );
        CREATE TABLE fields(fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData(itemID INTEGER, fieldID INTEGER, valueID INTEGER,
                              PRIMARY KEY(itemID, fieldID));
        CREATE TABLE creators(creatorID INTEGER PRIMARY KEY, firstName TEXT,
                              lastName TEXT, fieldMode INTEGER);
        CREATE TABLE creatorTypes(creatorTypeID INTEGER PRIMARY KEY,
                                  creatorType TEXT);
        CREATE TABLE itemCreators(itemID INTEGER, creatorID INTEGER,
                                  creatorTypeID INTEGER, orderIndex INTEGER,
                                  PRIMARY KEY(itemID, creatorID, orderIndex));
        """)
        for fid, fname in [(1, "title"), (14, "date"), (13, "url"),
                            (2, "abstractNote"), (59, "DOI")]:
            db.execute("INSERT INTO fields VALUES(?, ?)", (fid, fname))
        db.execute("INSERT INTO libraries VALUES(10, 'feed')")
        db.execute("INSERT INTO feeds VALUES(10,'F','http://f',NULL,NULL,NULL,60)")
        db.execute("INSERT INTO items VALUES(1001, 10, '2024-01-01', '2024-01-01')")
        db.execute("INSERT INTO feedItems VALUES(1001, 'g1', NULL, NULL)")
        db.execute("INSERT INTO itemDataValues VALUES(1, 'Test Title')")
        db.execute("INSERT INTO itemData VALUES(1001, 1, 1)")
        db.execute("INSERT INTO itemDataValues VALUES(2, '10.1234/test')")
        db.execute("INSERT INTO itemData VALUES(1001, 59, 2)")
        db.execute("INSERT INTO itemDataValues VALUES(3, 'https://example.com')")
        db.execute("INSERT INTO itemData VALUES(1001, 13, 3)")
        db.commit()
        db.close()
        reader = SQLiteReader(SQLiteConfig(path=str(db_path)))
        yield reader
        reader.close()

    def test_returns_all_item_data_fields(self, reader: SQLiteReader) -> None:
        result = reader.query_item_data([1001])
        assert 1001 in result
        fields = result[1001]
        assert fields["title"] == "Test Title"
        assert fields["DOI"] == "10.1234/test"
        assert fields["url"] == "https://example.com"

    def test_empty_input_returns_empty(self, reader: SQLiteReader) -> None:
        assert reader.query_item_data([]) == {}

    def test_unknown_id_not_in_result(self, reader: SQLiteReader) -> None:
        result = reader.query_item_data([9999])
        assert 9999 not in result
