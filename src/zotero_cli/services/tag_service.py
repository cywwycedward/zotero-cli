"""TagService — tag listing, add/remove on items, rename, delete."""

import builtins
from typing import Any

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.results import ListServiceResult, MutationServiceResult


class TagService:
    """Tag CRUD operations."""

    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    @classmethod
    def from_profile(cls, profile: Any) -> "TagService":
        return cls(ZoteroAPI(profile))

    def list(self) -> ListServiceResult:
        tags = self._api.tags()
        for t in tags:
            t["key"] = t.get("tag", "")
        return {
            "data": tags,
            "meta_extra": {"count": len(tags), "total": len(tags)},
        }

    def add(self, tag: str, item_keys: builtins.list[str]) -> MutationServiceResult:
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

    def remove(self, tag: str, item_keys: builtins.list[str]) -> MutationServiceResult:
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

    def rename(self, old: str, new: str) -> MutationServiceResult:
        """Rename a tag: find all items with old tag, replace with new."""
        all_items = self._api.items(limit=10000)
        affected: list[Any] = []
        for idx, item in enumerate(all_items):
            tags_list = item.get("data", {}).get("tags", [])
            tag_names = [t.get("tag", "") for t in tags_list]
            if old in tag_names:
                new_tags = []
                for t in tags_list:
                    name = t.get("tag", "")
                    if name == old:
                        new_tags.append({"tag": new})
                    elif name == new:
                        pass  # skip duplicate
                    else:
                        new_tags.append(t)
                item["data"]["tags"] = new_tags
                self._api.update_item(item)
                affected.append({"index": idx, "key": item.get("key", ""), "version": 0})
        return {
            "data": {
                "successful": affected,
                "unchanged": [],
                "failed": [],
            },
            "meta_extra": {"affected_keys": [a["key"] for a in affected]},
        }

    def delete(self, tag: str) -> MutationServiceResult:
        """Delete a tag entirely. affected_keys = items that held this tag."""
        all_items = self._api.items(limit=10000)
        affected_keys = [
            item.get("key", "")
            for item in all_items
            if tag in [t.get("tag", "") for t in item.get("data", {}).get("tags", [])]
        ]

        self._api.delete_tags(tag)

        return {
            "data": {
                "successful": [{"index": 0, "key": tag, "version": 0}],
                "unchanged": [],
                "failed": [],
            },
            "meta_extra": {"affected_keys": affected_keys},
        }
