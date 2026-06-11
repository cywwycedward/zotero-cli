"""ItemService — coordinates ZoteroAPI calls for item CRUD.

Per design §7.1: services return dict/list data, never format output.
Per DEVELOPMENT.md §4.2: all public methods return TypedDicts from models/results.py.
"""

import builtins
from typing import Any

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.errors import ApiServerError, CLIError, from_code
from zotero_cli.models.results import (
    ListServiceResult,
    MutationServiceResult,
    MutationSuccessfulItem,
    ShowServiceResult,
)


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
