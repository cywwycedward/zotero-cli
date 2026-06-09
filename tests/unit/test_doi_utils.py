"""tests/unit/test_doi_utils.py"""

from __future__ import annotations

import pytest

from zotero_cli.utils.doi import normalize_doi, validate_doi


class TestNormalizeDoi:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("10.1038/s41586-020-2649-2", "10.1038/s41586-020-2649-2"),
            ("  10.1038/s41586-020-2649-2  ", "10.1038/s41586-020-2649-2"),
            ("doi:10.1038/s41586-020-2649-2", "10.1038/s41586-020-2649-2"),
            ("DOI:10.1038/s41586-020-2649-2", "10.1038/s41586-020-2649-2"),
            (
                "https://doi.org/10.1038/s41586-020-2649-2",
                "10.1038/s41586-020-2649-2",
            ),
            (
                "http://doi.org/10.1038/s41586-020-2649-2",
                "10.1038/s41586-020-2649-2",
            ),
            (
                "https://dx.doi.org/10.1038/s41586-020-2649-2",
                "10.1038/s41586-020-2649-2",
            ),
            (
                "http://dx.doi.org/10.1038/s41586-020-2649-2",
                "10.1038/s41586-020-2649-2",
            ),
            (
                "https://doi.org/10.1000/a%23b",
                "10.1000/a#b",
            ),
            (
                "https://doi.org/10.1000/a%3Fb",
                "10.1000/a?b",
            ),
        ],
    )
    def test_normalizes_various_formats(self, raw: str, expected: str) -> None:
        assert normalize_doi(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("10.1038/s41586-020-2649-2.", "10.1038/s41586-020-2649-2"),
            ("10.1038/s41586-020-2649-2,", "10.1038/s41586-020-2649-2"),
            ("10.1038/s41586-020-2649-2;", "10.1038/s41586-020-2649-2"),
            ("10.1038/s41586-020-2649-2:", "10.1038/s41586-020-2649-2"),
            ("10.1038/s41586-020-2649-2)", "10.1038/s41586-020-2649-2"),
            ("10.1038/s41586-020-2649-2]", "10.1038/s41586-020-2649-2"),
        ],
    )
    def test_strips_trailing_punctuation(self, raw: str, expected: str) -> None:
        assert normalize_doi(raw) == expected

    def test_none_returns_none(self) -> None:
        assert normalize_doi(None) is None

    def test_empty_returns_none(self) -> None:
        assert normalize_doi("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert normalize_doi("   ") is None


class TestValidateDoi:
    @pytest.mark.parametrize(
        "doi",
        [
            "10.1038/s41586-020-2649-2",
            "10.1000/xyz123",
            "10.12345/some.thing-here",
        ],
    )
    def test_valid_dois(self, doi: str) -> None:
        assert validate_doi(doi) is True

    @pytest.mark.parametrize(
        "doi",
        [
            "not-a-doi",
            "11.1038/xyz",
            "10.123/xyz",
            "10.1234/",
            "",
        ],
    )
    def test_invalid_dois(self, doi: str) -> None:
        assert validate_doi(doi) is False
