"""src/zotero_cli/adapters/doi_metadata/crossref.py — CrossRef metadata provider."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

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

        body: dict[str, Any] = resp.json()
        message = body.get("message")
        if message is None:
            raise ApiServerError(
                "CrossRef response missing 'message' field",
                context={"doi": doi, "source": "crossref"},
            )
        return cast("dict[str, Any]", message)

    def to_zotero_item(
        self,
        raw: dict[str, Any],
        *,
        doi: str,
        item_template: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        crossref_type = raw.get("type", "")
        zotero_type = _CROSSREF_TYPE_MAP.get(crossref_type, "document")
        template = item_template(zotero_type)
        valid_keys = set(template.keys())

        payload: dict[str, Any] = {"itemType": zotero_type}

        titles = raw.get("title")
        if isinstance(titles, list) and titles:
            payload["title"] = titles[0]

        payload["DOI"] = raw.get("DOI", doi)

        if "URL" in raw:
            payload["url"] = raw["URL"]

        for cr_field, z_field in [("volume", "volume"), ("issue", "issue"), ("page", "pages")]:
            if raw.get(cr_field):
                payload[z_field] = raw[cr_field]

        if raw.get("publisher"):
            payload["publisher"] = raw["publisher"]

        for array_field in ["ISSN", "ISBN"]:
            arr = raw.get(array_field)
            if isinstance(arr, list) and arr:
                payload[array_field] = arr[0]

        container = raw.get("container-title")
        if isinstance(container, list) and container:
            field_name = _CONTAINER_FIELD.get(zotero_type)
            if field_name:
                payload[field_name] = container[0]

        payload["creators"] = self._map_creators(raw)

        date_str = self._extract_date(raw)
        if date_str:
            payload["date"] = date_str

        abstract = raw.get("abstract")
        if abstract:
            payload["abstractNote"] = _JATS_TAG_RE.sub("", abstract).strip()

        cleaned: dict[str, Any] = {}
        for k, v in payload.items():
            if k not in valid_keys and k not in ("itemType",):
                continue
            if v == "" or v == [] or v == {}:
                continue
            cleaned[k] = v
        cleaned["itemType"] = zotero_type
        if "creators" not in cleaned:
            cleaned["creators"] = []
        return cleaned

    @staticmethod
    def _map_creators(raw: dict[str, Any]) -> list[dict[str, Any]]:
        creators: list[dict[str, Any]] = []
        for role, creator_type in [("author", "author"), ("editor", "editor")]:
            for person in raw.get(role, []):
                if "family" in person:
                    creators.append(
                        {
                            "creatorType": creator_type,
                            "firstName": person.get("given", ""),
                            "lastName": person["family"],
                        }
                    )
                elif "name" in person:
                    creators.append(
                        {
                            "creatorType": creator_type,
                            "name": person["name"],
                        }
                    )
        return creators

    @staticmethod
    def _extract_date(raw: dict[str, Any]) -> str:
        for key in _DATE_KEYS:
            date_obj = raw.get(key)
            if date_obj and "date-parts" in date_obj:
                parts = date_obj["date-parts"]
                if isinstance(parts, list) and parts:
                    dp = parts[0]
                    if isinstance(dp, list) and dp:
                        return "-".join(str(p) for p in dp)
        return ""
