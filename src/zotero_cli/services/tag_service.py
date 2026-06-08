"""TagService — tag listing, add/remove on items, rename, delete."""
from typing import Any, Dict, List

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.results import ListServiceResult, MutationServiceResult


class TagService:
    """Tag CRUD operations."""

    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    def list(self) -> ListServiceResult:
        tags = self._api.tags()
        for t in tags:
            t["key"] = t.get("tag", "")
        return {
            "data": tags,
            "meta_extra": {"count": len(tags), "total": len(tags)},
        }

    def add(self, tag: str, item_keys: List[str]) -> MutationServiceResult:
        successful: list[Any] = []
        unchanged: list[Any] = []
        for idx, ik in enumerate(item_keys):
            item = self._api.item(ik)
            existing = [t.get("tag", "") for t in item.get("data", {}).get("tags", [])]
            if tag not in existing:
                existing.append(tag)
                item["data"]["tags"] = [{"tag": t} for t in existing]
                self._api.update_item(item)
                successful.append({"index": idx, "key": ik, "version": 0})
            else:
                unchanged.append({"index": idx, "key": ik})
        return {
            "data": {"successful": successful, "unchanged": unchanged, "failed": []},
            "meta_extra": {"affected_keys": [s["key"] for s in successful]},
        }

    def remove(self, tag: str, item_keys: List[str]) -> MutationServiceResult:
        successful: list[Any] = []
        for idx, ik in enumerate(item_keys):
            item = self._api.item(ik)
            existing = [t.get("tag", "") for t in item.get("data", {}).get("tags", [])]
            if tag in existing:
                existing.remove(tag)
                item["data"]["tags"] = [{"tag": t} for t in existing]
                self._api.update_item(item)
                successful.append({"index": idx, "key": ik, "version": 0})
        return {
            "data": {"successful": successful, "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": [s["key"] for s in successful]},
        }

    def delete(self, tag: str) -> MutationServiceResult:
        self._api.delete_tags(tag)
        return {
            "data": {"successful": [{"index": 0, "key": tag, "version": 0}], "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": []},
        }
