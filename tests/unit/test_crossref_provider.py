"""tests/unit/test_crossref_provider.py"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from zotero_cli.adapters.doi_metadata.crossref import CrossrefProvider
from zotero_cli.models.errors import (
    ApiRateLimitError,
    ApiServerError,
    ApiTimeoutError,
    DoiNotFoundError,
    NetworkError,
)

SAMPLE_CROSSREF_MESSAGE: dict[str, Any] = {
    "status": "ok",
    "message": {
        "type": "journal-article",
        "DOI": "10.1038/s41586-020-2649-2",
        "title": ["Array programming with NumPy"],
        "author": [{"given": "Charles R.", "family": "Harris"}],
        "container-title": ["Nature"],
        "published-print": {"date-parts": [[2020, 9, 17]]},
        "volume": "585",
        "issue": "7825",
        "page": "357-362",
        "publisher": "Springer Science and Business Media LLC",
        "ISSN": ["0028-0836", "1476-4687"],
        "URL": "http://dx.doi.org/10.1038/s41586-020-2649-2",
        "abstract": "<jats:p>Some abstract text</jats:p>",
    },
}


class TestFetch:
    @respx.mock
    def test_successful_fetch(self) -> None:
        route = respx.get("https://api.crossref.org/works/10.1038/s41586-020-2649-2").mock(
            return_value=httpx.Response(200, json=SAMPLE_CROSSREF_MESSAGE)
        )
        provider = CrossrefProvider()
        raw = provider.fetch("10.1038/s41586-020-2649-2")
        assert raw["DOI"] == "10.1038/s41586-020-2649-2"
        assert raw["title"] == ["Array programming with NumPy"]
        assert route.called

    @respx.mock
    def test_fetch_with_mailto(self) -> None:
        route = respx.get(
            "https://api.crossref.org/works/10.1038/s41586-020-2649-2",
            params={"mailto": "user@example.com"},
        ).mock(return_value=httpx.Response(200, json=SAMPLE_CROSSREF_MESSAGE))
        provider = CrossrefProvider(crossref_email="user@example.com")
        provider.fetch("10.1038/s41586-020-2649-2")
        assert route.called

    @respx.mock
    def test_user_agent_header(self) -> None:
        route = respx.get("https://api.crossref.org/works/10.1038/s41586-020-2649-2").mock(
            return_value=httpx.Response(200, json=SAMPLE_CROSSREF_MESSAGE)
        )
        provider = CrossrefProvider()
        provider.fetch("10.1038/s41586-020-2649-2")
        request = route.calls[0].request
        assert "zotero-cli" in request.headers["user-agent"]

    @respx.mock
    def test_user_agent_includes_mailto(self) -> None:
        route = respx.get(
            "https://api.crossref.org/works/10.1038/s41586-020-2649-2",
            params={"mailto": "u@e.com"},
        ).mock(return_value=httpx.Response(200, json=SAMPLE_CROSSREF_MESSAGE))
        provider = CrossrefProvider(crossref_email="u@e.com")
        provider.fetch("10.1038/s41586-020-2649-2")
        request = route.calls[0].request
        assert "mailto:u@e.com" in request.headers["user-agent"]

    @respx.mock
    def test_404_raises_doi_not_found(self) -> None:
        respx.get("https://api.crossref.org/works/10.9999/notreal").mock(
            return_value=httpx.Response(404)
        )
        provider = CrossrefProvider()
        with pytest.raises(DoiNotFoundError):
            provider.fetch("10.9999/notreal")

    @respx.mock
    def test_429_raises_rate_limit(self) -> None:
        respx.get("https://api.crossref.org/works/10.1038/test").mock(
            return_value=httpx.Response(429)
        )
        provider = CrossrefProvider()
        with pytest.raises(ApiRateLimitError):
            provider.fetch("10.1038/test")

    @respx.mock
    def test_500_raises_server_error(self) -> None:
        respx.get("https://api.crossref.org/works/10.1038/test").mock(
            return_value=httpx.Response(500)
        )
        provider = CrossrefProvider()
        with pytest.raises(ApiServerError):
            provider.fetch("10.1038/test")

    @respx.mock
    def test_timeout_raises_api_timeout(self) -> None:
        respx.get("https://api.crossref.org/works/10.1038/test").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        provider = CrossrefProvider()
        with pytest.raises(ApiTimeoutError):
            provider.fetch("10.1038/test")

    @respx.mock
    def test_connection_error_raises_network_error(self) -> None:
        respx.get("https://api.crossref.org/works/10.1038/test").mock(
            side_effect=httpx.ConnectError("DNS failed")
        )
        provider = CrossrefProvider()
        with pytest.raises(NetworkError):
            provider.fetch("10.1038/test")

    @respx.mock
    def test_missing_message_raises_server_error(self) -> None:
        respx.get("https://api.crossref.org/works/10.1038/test").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        provider = CrossrefProvider()
        with pytest.raises(ApiServerError, match="message"):
            provider.fetch("10.1038/test")


def _fake_template(item_type: str) -> dict[str, Any]:
    """Minimal Zotero template for testing — only fields that are valid."""
    base: dict[str, Any] = {
        "itemType": "",
        "title": "",
        "creators": [],
        "date": "",
        "DOI": "",
        "url": "",
        "abstractNote": "",
        "tags": [],
        "collections": [],
    }
    type_fields: dict[str, list[str]] = {
        "journalArticle": ["publicationTitle", "volume", "issue", "pages", "ISSN", "publisher"],
        "conferencePaper": ["proceedingsTitle", "volume", "pages", "publisher"],
        "book": ["publisher", "ISBN", "volume"],
        "bookSection": ["bookTitle", "publisher", "ISBN", "pages", "volume"],
        "report": ["publisher"],
        "thesis": ["publisher"],
        "preprint": ["publisher"],
        "document": ["publisher"],
    }
    for f in type_fields.get(item_type, []):
        base[f] = ""
    base["itemType"] = item_type
    return base


class TestTypeMapping:
    @pytest.mark.parametrize(
        "crossref_type, zotero_type",
        [
            ("journal-article", "journalArticle"),
            ("proceedings-article", "conferencePaper"),
            ("book", "book"),
            ("book-chapter", "bookSection"),
            ("report", "report"),
            ("dissertation", "thesis"),
            ("posted-content", "preprint"),
            ("monograph", "book"),
            ("edited-book", "book"),
            ("unknown-type", "document"),
        ],
    )
    def test_type_map(self, crossref_type: str, zotero_type: str) -> None:
        provider = CrossrefProvider()
        raw = {"type": crossref_type, "title": ["Test"], "DOI": "10.1000/test"}
        result = provider.to_zotero_item(raw, doi="10.1000/test", item_template=_fake_template)
        assert result["itemType"] == zotero_type


class TestFieldMapping:
    def _build(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "type": "journal-article",
            "title": ["Test Title"],
            "DOI": "10.1000/test",
        }
        base.update(overrides)
        return base

    def _convert(self, raw: dict[str, Any]) -> dict[str, Any]:
        provider = CrossrefProvider()
        return provider.to_zotero_item(
            raw, doi=raw.get("DOI", "10.1000/test"), item_template=_fake_template
        )

    def test_title(self) -> None:
        result = self._convert(self._build(title=["My Paper Title"]))
        assert result["title"] == "My Paper Title"

    def test_doi_from_raw(self) -> None:
        result = self._convert(self._build(DOI="10.1234/abc"))
        assert result["DOI"] == "10.1234/abc"

    def test_doi_fallback_to_arg(self) -> None:
        raw = self._build()
        del raw["DOI"]
        provider = CrossrefProvider()
        result = provider.to_zotero_item(raw, doi="10.9999/fallback", item_template=_fake_template)
        assert result["DOI"] == "10.9999/fallback"

    def test_url(self) -> None:
        result = self._convert(self._build(URL="https://example.com/paper"))
        assert result["url"] == "https://example.com/paper"

    def test_volume_issue_pages(self) -> None:
        result = self._convert(self._build(volume="10", issue="3", page="100-110"))
        assert result["volume"] == "10"
        assert result["issue"] == "3"
        assert result["pages"] == "100-110"

    def test_publisher(self) -> None:
        result = self._convert(self._build(publisher="Nature Publishing Group"))
        assert result["publisher"] == "Nature Publishing Group"

    def test_issn_takes_first(self) -> None:
        result = self._convert(self._build(ISSN=["0028-0836", "1476-4687"]))
        assert result["ISSN"] == "0028-0836"

    def test_isbn_takes_first(self) -> None:
        raw = self._build(type="book", ISBN=["978-3-16-148410-0", "978-0-00-000000-0"])
        result = self._convert(raw)
        assert result["ISBN"] == "978-3-16-148410-0"

    def test_container_title_journal(self) -> None:
        raw = self._build(**{"container-title": ["Nature"]})
        result = self._convert(raw)
        assert result["publicationTitle"] == "Nature"

    def test_container_title_conference(self) -> None:
        raw = self._build(type="proceedings-article", **{"container-title": ["NeurIPS 2024"]})
        result = self._convert(raw)
        assert result["proceedingsTitle"] == "NeurIPS 2024"

    def test_container_title_book_section(self) -> None:
        raw = self._build(type="book-chapter", **{"container-title": ["Handbook of ML"]})
        result = self._convert(raw)
        assert result["bookTitle"] == "Handbook of ML"


class TestCreatorMapping:
    def _convert(self, raw: dict[str, Any]) -> dict[str, Any]:
        provider = CrossrefProvider()
        return provider.to_zotero_item(raw, doi="10.1000/test", item_template=_fake_template)

    def test_personal_author(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "author": [{"given": "Alice", "family": "Smith"}],
        }
        result = self._convert(raw)
        assert result["creators"] == [
            {"creatorType": "author", "firstName": "Alice", "lastName": "Smith"}
        ]

    def test_institutional_author(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "author": [{"name": "WHO"}],
        }
        result = self._convert(raw)
        assert result["creators"] == [
            {"creatorType": "author", "name": "WHO"}
        ]

    def test_editor(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "editor": [{"given": "Bob", "family": "Jones"}],
        }
        result = self._convert(raw)
        assert result["creators"] == [
            {"creatorType": "editor", "firstName": "Bob", "lastName": "Jones"}
        ]

    def test_author_missing_given(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "author": [{"family": "OnlyLast"}],
        }
        result = self._convert(raw)
        assert result["creators"] == [
            {"creatorType": "author", "firstName": "", "lastName": "OnlyLast"}
        ]

    def test_empty_creator_skipped(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "author": [{}],
        }
        result = self._convert(raw)
        assert result["creators"] == []


class TestDateMapping:
    def _convert(self, raw: dict[str, Any]) -> dict[str, Any]:
        provider = CrossrefProvider()
        return provider.to_zotero_item(raw, doi="10.1000/test", item_template=_fake_template)

    def test_published_print_priority(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "published-print": {"date-parts": [[2024, 3, 15]]},
            "published-online": {"date-parts": [[2024, 2, 1]]},
        }
        result = self._convert(raw)
        assert result["date"] == "2024-3-15"

    def test_year_only(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "issued": {"date-parts": [[2024]]},
        }
        result = self._convert(raw)
        assert result["date"] == "2024"

    def test_year_month(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "published": {"date-parts": [[2024, 7]]},
        }
        result = self._convert(raw)
        assert result["date"] == "2024-7"

    def test_no_date_field_omitted(self) -> None:
        raw = {"type": "journal-article", "title": ["T"], "DOI": "10.1000/t"}
        result = self._convert(raw)
        assert result.get("date", "") == ""


class TestAbstractCleaning:
    def _convert(self, raw: dict[str, Any]) -> dict[str, Any]:
        provider = CrossrefProvider()
        return provider.to_zotero_item(raw, doi="10.1000/test", item_template=_fake_template)

    def test_strips_jats_tags(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "abstract": "<jats:p>Some <jats:italic>abstract</jats:italic> text</jats:p>",
        }
        result = self._convert(raw)
        assert result["abstractNote"] == "Some abstract text"

    def test_plain_abstract(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "abstract": "Plain abstract.",
        }
        result = self._convert(raw)
        assert result["abstractNote"] == "Plain abstract."


class TestPayloadCleaning:
    def _convert(self, raw: dict[str, Any]) -> dict[str, Any]:
        provider = CrossrefProvider()
        return provider.to_zotero_item(raw, doi="10.1000/test", item_template=_fake_template)

    def test_non_template_fields_excluded(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "random-crossref-field": "should be ignored",
        }
        result = self._convert(raw)
        assert "random-crossref-field" not in result

    def test_empty_strings_removed(self) -> None:
        raw = {
            "type": "journal-article",
            "title": ["T"],
            "DOI": "10.1000/t",
            "volume": "",
        }
        result = self._convert(raw)
        assert "volume" not in result or result.get("volume") != ""
