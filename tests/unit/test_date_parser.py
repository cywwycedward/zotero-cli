"""Tests for date_parser -- regex patterns, month validator, and DateRange."""
from __future__ import annotations

import pytest

from zotero_cli.models.errors import InvalidDateFormatError
from zotero_cli.utils.date_parser import (
    ISO_DATE_RE,
    YEAR_MONTH_RE,
    YEAR_RE,
    DateRange,
    _to_end_bound,
    _to_start_bound,
    _validate_month,
    date_range_to_sql_bounds,
)

YEAR_MATCHES = ["2024", "1900", "9999"]
YEAR_REJECTS = ["24", "20240", "2024a", "2024-"]
YEAR_MONTH_MATCHES = ["2024-01", "2024-12"]
YEAR_MONTH_REJECTS = ["2024-1", "2024/01"]
ISO_DATE_MATCHES = ["2024-01-01", "2024-12-31", "1900-06-15"]
ISO_DATE_REJECTS = ["2024-1-1", "2024/01/01", "24-01-01"]
VALID_MONTHS = [1, 6, 12]
INVALID_MONTHS = [0, 13, -1, 100]


@pytest.mark.parametrize("s", YEAR_MATCHES)
def test_year_re_matches(s: str) -> None:
    assert YEAR_RE.match(s) is not None


@pytest.mark.parametrize("s", YEAR_REJECTS)
def test_year_re_rejects(s: str) -> None:
    assert YEAR_RE.match(s) is None


@pytest.mark.parametrize("s", YEAR_MONTH_MATCHES)
def test_year_month_re_matches(s: str) -> None:
    assert YEAR_MONTH_RE.match(s) is not None


@pytest.mark.parametrize("s", YEAR_MONTH_REJECTS)
def test_year_month_re_rejects(s: str) -> None:
    assert YEAR_MONTH_RE.match(s) is None


@pytest.mark.parametrize("s", ISO_DATE_MATCHES)
def test_iso_date_re_matches(s: str) -> None:
    assert ISO_DATE_RE.match(s) is not None


@pytest.mark.parametrize("s", ISO_DATE_REJECTS)
def test_iso_date_re_rejects(s: str) -> None:
    assert ISO_DATE_RE.match(s) is None


@pytest.mark.parametrize("month", VALID_MONTHS)
def test_validate_month_accepts_valid(month: int) -> None:
    _validate_month(2024, month)  # should not raise


@pytest.mark.parametrize("month", INVALID_MONTHS)
def test_validate_month_rejects_invalid(month: int) -> None:
    with pytest.raises(InvalidDateFormatError):
        _validate_month(2024, month)


def test_date_range_dataclass() -> None:
    dr = DateRange("2024-01-01", "2024-12-31")
    assert dr.start == "2024-01-01"
    assert dr.end == "2024-12-31"


BOUNDS_CASES = [
    ("2024", "2024-00-00", "2024-12-31"),
    ("2024-06", "2024-06-00", "2024-06-30"),
    ("2024-02", "2024-02-00", "2024-02-29"),  # leap year
    ("2023-02", "2023-02-00", "2023-02-28"),  # non-leap
    ("2024-06-15", "2024-06-15", "2024-06-15"),
    ("2024-12-31", "2024-12-31", "2024-12-31"),
]


@pytest.mark.parametrize("s,exp_start,exp_end", BOUNDS_CASES)
def test_bounds_start(
    s: str, exp_start: str, exp_end: str
) -> None:
    assert _to_start_bound(s) == exp_start


@pytest.mark.parametrize("s,exp_start,exp_end", BOUNDS_CASES)
def test_bounds_end(
    s: str, exp_start: str, exp_end: str
) -> None:
    assert _to_end_bound(s) == exp_end


INVALID_INPUTS = [
    "June 24",
    "2024/06",
    "24-06",
    "2024-13",
    "2024-1",
    "2024-02-30",
    "2023-02-29",
]


@pytest.mark.parametrize("s", INVALID_INPUTS)
def test_start_bound_invalid_input_raises(s: str) -> None:
    with pytest.raises(InvalidDateFormatError):
        _to_start_bound(s)


@pytest.mark.parametrize("s", INVALID_INPUTS)
def test_end_bound_invalid_input_raises(s: str) -> None:
    with pytest.raises(InvalidDateFormatError):
        _to_end_bound(s)


RANGE_CASES = [
    ("2024", DateRange("2024-00-00", "2024-12-31")),
    ("2024-06-15", DateRange("2024-06-15", "2024-06-15")),
    ("2024-01..2024-06", DateRange("2024-01-00", "2024-06-30")),
    ("2024-06-15..", DateRange("2024-06-15", "9999-12-31")),
    ("..2024-06-15", DateRange("0000-00-00", "2024-06-15")),
    ("..", DateRange("0000-00-00", "9999-12-31")),
]


@pytest.mark.parametrize("arg,expected", RANGE_CASES)
def test_date_range_to_sql_bounds(
    arg: str, expected: DateRange
) -> None:
    assert date_range_to_sql_bounds(arg) == expected


def test_whitespace_stripped() -> None:
    result = date_range_to_sql_bounds("  2024  ")
    assert result == DateRange("2024-00-00", "2024-12-31")


def test_range_with_spaces_around_dotdot() -> None:
    result = date_range_to_sql_bounds("2024-01 .. 2024-06")
    assert result == DateRange("2024-01-00", "2024-06-30")
