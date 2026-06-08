"""Date parsing utilities for Zotero date fields.

Per design §11.4: Zotero date fields use ISO 8601 year, year-month, or full-date
strings. This module provides regex constants, validation helpers, and a
function to convert user-facing date specs into SQL-compatible bounds.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime

from zotero_cli.models.errors import InvalidDateFormatError

YEAR_RE = re.compile(r"^\d{4}$")
YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class DateRange:
    """Represents an SQL-compatible date range with ``start`` and ``end`` bounds."""

    start: str
    end: str


def _validate_date(s: str) -> None:
    """Validate that *s* (YYYY-MM-DD) is a real calendar date."""
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError as err:
        raise InvalidDateFormatError(
            f"Invalid date '{s}'",
            hint=f"'{s}' is not a valid calendar date",
        ) from err


def _validate_month(year: int, month: int) -> None:
    if not (1 <= month <= 12):
        raise InvalidDateFormatError(
            f"Invalid month '{month:02d}' in date input",
            hint="Month must be 01-12",
        )


def _to_start_bound(s: str) -> str:
    """Convert a date string to its lower SQL bound."""
    if YEAR_RE.match(s):
        return f"{s}-00-00"
    if YEAR_MONTH_RE.match(s):
        year = int(s[:4])
        month = int(s[5:7])
        _validate_month(year, month)
        return f"{s}-00"
    if ISO_DATE_RE.match(s):
        _validate_date(s)
        return s
    raise InvalidDateFormatError(
        f"Unrecognized date format: '{s}'",
        hint="Expected formats: YYYY, YYYY-MM, or YYYY-MM-DD",
    )


def _to_end_bound(s: str) -> str:
    """Convert a date string to its upper SQL bound."""
    if YEAR_RE.match(s):
        return f"{s}-12-31"
    if YEAR_MONTH_RE.match(s):
        year = int(s[:4])
        month = int(s[5:7])
        _validate_month(year, month)
        last_day = calendar.monthrange(year, month)[1]
        return f"{s}-{last_day:02d}"
    if ISO_DATE_RE.match(s):
        _validate_date(s)
        return s
    raise InvalidDateFormatError(
        f"Unrecognized date format: '{s}'",
        hint="Expected formats: YYYY, YYYY-MM, or YYYY-MM-DD",
    )


def date_range_to_sql_bounds(arg: str) -> DateRange:
    """Convert a user-facing date spec to SQL-compatible start/end bounds.

    Parameters
    ----------
    arg:
        A single date (``2024``, ``2024-06``, ``2024-06-15``) or a range
        using ``..`` separator (``2024-01..2024-06``).

    Returns
    -------
    DateRange
        A dataclass with ``start`` and ``end`` strings suitable for SQL
        comparisons (``BETWEEN`` or ``>=`` / ``<=``).
    """
    arg = arg.strip()
    if ".." in arg:
        if arg.count("..") > 1:
            raise InvalidDateFormatError(
                f"Multiple '..' operators in date range: '{arg}'",
                hint="Use at most one '..' to specify a date range",
            )
        left, right = arg.split("..", maxsplit=1)
        left = left.strip()
        right = right.strip()
        start = _to_start_bound(left) if left else "0000-00-00"
        end = _to_end_bound(right) if right else "9999-12-31"
        return DateRange(start=start, end=end)
    return DateRange(start=_to_start_bound(arg), end=_to_end_bound(arg))
