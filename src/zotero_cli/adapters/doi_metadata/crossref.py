"""src/zotero_cli/adapters/doi_metadata/crossref.py — CrossRef metadata provider."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx

from zotero_cli.models.errors import (
    ApiRateLimitError,
    ApiServerError,
    ApiTimeoutError,
    DoiNotFoundError,
    NetworkError,
)

_CROSSREF_BASE = "https://api.crossref.org/works"
_JATS_TAG_RE = re.compile(r"<[^>]+>")


def _get_version() -> str:
    from importlib.metadata import version

    try:
        return version("zotero")
    except Exception:
        return "0.0.0"


_CROSSREF_TYPE_MAP: dict[str, str] = {
    "journal-article": "journalArticle",
    "proceedings-article": "conferencePaper",
    "book": "book",
    "book-chapter": "bookSection",
    "report": "report",
    "dissertation": "thesis",
    "posted-content": "preprint",
    "monograph": "book",
    "edited-book": "book",
}

_CONTAINER_FIELD: dict[str, str] = {
    "journalArticle": "publicationTitle",
    "conferencePaper": "proceedingsTitle",
    "bookSection": "bookTitle",
}

_DATE_KEYS = [
    "published-print",
    "published-online",
    "published",
    "issued",
    "created",
]


class CrossrefProvider:
    source: str = "crossref"

    def __init__(self, *, crossref_email: str | None = None) -> None:
        self._email = crossref_email

    def _user_agent(self) -> str:
        ua = f"zotero-cli/{_get_version()}"
        if self._email:
            ua += f" (mailto:{self._email})"
        return ua

    def fetch(self, doi: str) -> dict[str, Any]:
        url = f"{_CROSSREF_BASE}/{doi}"
        params: dict[str, str] = {}
        if self._email:
            params["mailto"] = self._email
        headers = {
            "Accept": "application/json",
            "User-Agent": self._user_agent(),
        }
        try:
            with httpx.Client() as client:
                resp = client.get(url, params=params, headers=headers, timeout=30)
        except httpx.TimeoutException as e:
            raise ApiTimeoutError(
                f"CrossRef request timed out for DOI {doi}",
                context={"doi": doi, "source": "crossref"},
            ) from e
        except httpx.ConnectError as e:
            raise NetworkError(
                f"Failed to connect to CrossRef for DOI {doi}",
                context={"doi": doi, "source": "crossref"},
            ) from e
        except httpx.HTTPError as e:
            raise NetworkError(
                f"HTTP error fetching DOI {doi} from CrossRef: {e}",
                context={"doi": doi, "source": "crossref"},
            ) from e

        if resp.status_code == 404:
            raise DoiNotFoundError(
                f"DOI {doi} not found on CrossRef",
                hint="Check the DOI is correct, or try a different source.",
                context={"doi": doi, "source": "crossref"},
            )
        if resp.status_code == 429:
            raise ApiRateLimitError(
                "CrossRef rate limit exceeded",
                hint="Wait a moment and try again, or configure crossref_email for polite pool.",
                context={"doi": doi, "source": "crossref"},
            )
        if resp.status_code >= 500:
            raise ApiServerError(
                f"CrossRef server error ({resp.status_code})",
                context={"doi": doi, "source": "crossref", "status": resp.status_code},
            )
        if resp.status_code != 200:
            raise ApiServerError(
                f"Unexpected CrossRef response ({resp.status_code})",
                context={"doi": doi, "source": "crossref", "status": resp.status_code},
            )

        body = resp.json()
        message = body.get("message")
        if message is None:
            raise ApiServerError(
                "CrossRef response missing 'message' field",
                context={"doi": doi, "source": "crossref"},
            )
        return message

    def to_zotero_item(
        self,
        raw: dict[str, Any],
        *,
        doi: str,
        item_template: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        # Implementation in Task 4
        raise NotImplementedError
