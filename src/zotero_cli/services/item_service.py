"""ItemService — coordinates ZoteroAPI calls for item CRUD.

Per design §7.1: services return dict/list data, never format output.
Per DEVELOPMENT.md §4.2: all public methods return TypedDicts from models/results.py.
"""

import builtins
from typing import Any

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.errors import ApiServerError, CLIError, InvalidFieldError, from_code
from zotero_cli.models.results import (
    FindByDoiServiceResult,
    ListServiceResult,
    MutationServiceResult,
    MutationSuccessfulItem,
    ShowServiceResult,
)
from zotero_cli.utils.doi import normalize_doi, validate_doi


class ItemService:
    """Item CRUD operations. Constructed per-command with a ZoteroAPI instance."""

    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    @classmethod
    def from_profile(cls, profile: Any) -> "ItemService":
        return cls(ZoteroAPI(profile))

    # -- Read --

    def list(
        self,
        *,
        limit: int = 100,
        start: int = 0,
        collection: str | None = None,
        tag: str | None = None,
    ) -> ListServiceResult:
        items = self._api.items_top(
            limit=limit,
            start=start,
            collection=collection,
            tag=tag,
        )
        total = self._api.count_items(collection=collection, tag=tag)
        return {
            "data": [_flatten_item(i) for i in items],
            "meta_extra": {
                "count": len(items),
                "total": total,
                "limit": limit,
                "start": start,
                "next_start": start + limit if start + limit < total else None,
                "library_id": self._api.library_id,
                "library_version": self._api.last_modified_version(),
            },
        }

    def search(
        self,
        query: str,
        *,
        limit: int = 100,
        start: int = 0,
    ) -> ListServiceResult:
        items = self._api.search_items(query, limit=limit, start=start)
        return {
            "data": [_flatten_item(i) for i in items],
            "meta_extra": {
                "count": len(items),
                "total": len(items),
                "limit": limit,
                "start": start,
                "next_start": None,
                "library_id": self._api.library_id,
                "library_version": self._api.last_modified_version(),
            },
        }

    def find_by_doi(
        self,
        raw_doi: str,
        *,
        collection: str | None = None,
    ) -> FindByDoiServiceResult:
        """Find items whose data.DOI matches *raw_doi* (normalized, case-insensitive).

        Zotero/pyzotero expose no DOI-field query, so we page through items_top
        — the bibliographic, top-level item set (DOIs never live on attachments
        or notes), the same set `items list` shows — over the whole library or a
        single collection, and match locally. An item with a missing, non-string,
        or unnormalizable DOI is skipped, never fatal (design §6.3 / §11).
        "No match" returns an empty list, not an error.
        """
        doi = normalize_doi(raw_doi)
        if doi is None or not validate_doi(doi):
            raise InvalidFieldError(
                f"Invalid DOI: {raw_doi!r}",
                hint="Provide a bare DOI (10.xxxx/yyyy), doi: prefix, or DOI URL.",
                context={"raw_input": raw_doi},
            )
        target = doi.lower()

        matches: list[dict[str, Any]] = []
        page_size = 100
        start = 0
        while True:
            page = self._api.items_top(limit=page_size, start=start, collection=collection)
            if not page:
                break
            for raw_item in page:
                flat = _flatten_item(raw_item)
                item_doi = flat.get("DOI")
                if not isinstance(item_doi, str):
                    continue
                normalized = normalize_doi(item_doi)
                if normalized is not None and normalized.lower() == target:
                    matches.append(flat)
            if len(page) < page_size:
                break
            start += page_size

        return {
            "data": matches,
            "meta_extra": {
                "count": len(matches),
                "total": len(matches),
                "query_doi": raw_doi,
                "normalized_doi": doi,
                "collection": collection,
                "library_id": self._api.library_id,
            },
        }

    def show(self, key: str) -> ShowServiceResult:
        data = self._api.item(key)
        return {"data": _flatten_item(data)}

    # -- Write --

    def create(self, payloads: builtins.list[dict[str, Any]]) -> MutationServiceResult:
        result = self._api.create_items(payloads)
        affected = [s["key"] for s in result["successful"]]
        return {
            "data": result,  # type: ignore[typeddict-item]
            "meta_extra": {"affected_keys": affected},
        }

    def create_single(self, payload: dict[str, Any]) -> MutationSuccessfulItem:
        result = self.create([payload])
        data = result["data"]
        if data["successful"]:
            return data["successful"][0]
        if data["failed"]:
            failed = data["failed"][0]
            raise from_code(
                failed["code"],
                failed["message"],
                context=failed.get("context"),
            )
        raise ApiServerError(
            "Zotero create returned no successful or failed item",
            context={"payload_count": 1},
        )

    def update(self, key: str, *, patch: dict[str, Any]) -> MutationServiceResult:
        item = self._api.item(key)
        data = item.get("data", {})
        merged = dict(data)

        add_tags = patch.get("add_tags")
        api_patch = {k: v for k, v in patch.items() if k != "add_tags"}
        merged.update(api_patch)

        if add_tags:
            existing = {t["tag"] for t in merged.get("tags", [])}
            for tag_name in add_tags:
                if tag_name not in existing:
                    merged.setdefault("tags", []).append({"tag": tag_name})
                    existing.add(tag_name)

        item["data"] = merged
        self._api.update_item(item)
        return {
            "data": {
                "successful": [
                    {"index": 0, "key": key, "version": item.get("version", 0), "data": merged},
                ],
                "unchanged": [],
                "failed": [],
            },
            "meta_extra": {"affected_keys": [key]},
        }

    def delete(self, keys: builtins.list[str]) -> MutationServiceResult:
        successful: list[Any] = []
        failed: list[Any] = []
        for idx, item_key in enumerate(keys):
            try:
                item = self._api.item(item_key)
                self._api.delete_item(item)
                successful.append({"index": idx, "key": item_key, "version": 0})
            except CLIError as e:
                failed.append(
                    {
                        "index": idx,
                        "code": e.code,
                        "message": e.message,
                    }
                )
        return {
            "data": {
                "successful": successful,
                "unchanged": [],
                "failed": failed,
            },
            "meta_extra": {"affected_keys": [s["key"] for s in successful]},
        }


def _flatten_item(item: dict[str, Any]) -> dict[str, Any]:
    """Merge item['data'] fields to top level for display.

    Pyzotero returns {"key":"X","data":{"title":"...","creators":[...],...},...}.
    Field filters operate on top-level keys, so we need title/creators/etc at top level.
    Already-flat dicts (e.g. from mocks) pass through unchanged.
    """
    if "data" not in item or not isinstance(item["data"], dict):
        return item
    flat = dict(item["data"])
    flat["key"] = item.get("key", flat.get("key", ""))
    return flat
