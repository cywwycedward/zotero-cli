"""src/zotero_cli/services/doi_item_service.py — Orchestrates DOI-to-Zotero-item creation."""

from __future__ import annotations

from typing import Any

from zotero_cli.adapters.doi_metadata.base import DoiMetadataProvider
from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.errors import ApiServerError, InvalidFieldError
from zotero_cli.services.item_service import ItemService
from zotero_cli.utils.doi import normalize_doi, validate_doi


class DoiItemService:
    def __init__(
        self,
        *,
        api: ZoteroAPI,
        item_service: ItemService,
        provider: DoiMetadataProvider,
    ) -> None:
        self._api = api
        self._item_service = item_service
        self._provider = provider

    def add_by_doi(
        self,
        raw_doi: str,
        *,
        dry_run: bool = False,
        tags: list[str] | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        doi = normalize_doi(raw_doi)
        if doi is None or not validate_doi(doi):
            raise InvalidFieldError(
                f"Invalid DOI: {raw_doi!r}",
                hint="Provide a bare DOI (10.xxxx/yyyy), doi: prefix, or DOI URL.",
                context={"raw_input": raw_doi},
            )

        raw = self._provider.fetch(doi)
        payload = self._provider.to_zotero_item(
            raw,
            doi=doi,
            item_template=self._api.item_template,
        )

        missing = [
            f for f in ("itemType", "title", "DOI") if not payload.get(f)
        ]
        if missing:
            raise ApiServerError(
                f"CrossRef metadata missing required fields: {', '.join(missing)}; cannot create item",
                context={"doi": doi, "source": self._provider.source, "missing": missing},
            )

        if tags:
            payload["tags"] = [{"tag": t} for t in tags]
        if collection:
            payload["collections"] = [collection]

        meta: dict[str, Any] = {
            "source": self._provider.source,
            "normalized_doi": doi,
        }

        if dry_run:
            return {
                "data": {"dry_run": True, "would_create": [payload]},
                "meta_extra": {**meta, "dry_run": True},
            }

        result = self._item_service.create([payload])
        affected = result["meta_extra"].get("affected_keys", [])
        return {
            "data": result["data"],
            "meta_extra": {**meta, "affected_keys": affected},
        }
