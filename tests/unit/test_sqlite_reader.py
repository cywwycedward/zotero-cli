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
