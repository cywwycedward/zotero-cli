"""Tests for date_parser -- regex patterns, month validator, and DateRange."""
from __future__ import annotations

import pytest

from zotero_cli.models.errors import InvalidDateFormatError
from zotero_cli.utils.date_parser import (
    ISO_DATE_RE,
    YEAR_MONTH_RE,
    YEAR_RE,
    DateRange,
    _validate_month,
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
