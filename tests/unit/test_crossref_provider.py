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
