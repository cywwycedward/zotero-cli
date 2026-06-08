"""Date parsing utilities for Zotero date fields.

Per design §11.4: Zotero date fields use ISO 8601 year, year-month, or full-date
strings. This module provides regex constants, validation helpers, and a
function to convert user-facing date specs into SQL-compatible bounds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from zotero_cli.models.errors import InvalidDateFormatError

YEAR_RE = re.compile(r"^\d{4}$")
YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class DateRange:
    """Represents an SQL-compatible date range with ``start`` and ``end`` bounds."""

    start: str
    end: str


def _validate_month(year: int, month: int) -> None:
    if not (1 <= month <= 12):
        raise InvalidDateFormatError(
            f"Invalid month '{month:02d}' in date input",
            hint="Month must be 01-12",
        )
