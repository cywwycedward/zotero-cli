"""CollectionService — CRUD + tree building for collections."""
from typing import Any, Dict, List

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.results import (
    CollectionNode,
    CollectionTreeServiceResult,
    MutationServiceResult,
    ShowServiceResult,
)


class CollectionService:
    """Collection CRUD operations."""

    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    def list(self) -> CollectionTreeServiceResult:
        raw = self._api.collections()
        by_key: Dict[str, dict[str, Any]] = {c["key"]: c for c in raw}
        children_map: Dict[str, List[dict[str, Any]]] = {}
        roots: List[dict[str, Any]] = []
        for c in raw:
            parent = c.get("parentCollection")
            if parent is False or parent is None or parent == "":
                roots.append(c)
            else:
                parent_key = parent if isinstance(parent, str) else str(parent)
                if parent_key in by_key:
                    children_map.setdefault(parent_key, []).append(c)
                else:
                    roots.append(c)  # orphan: parent not found → treat as root

        def _build(node: dict[str, Any]) -> CollectionNode:
            key = node.get("key", "")
            return {
                "key": key,
                "name": node.get("data", {}).get("name", node.get("name", "")),
                "items_count": node.get("meta", {}).get("numItems", node.get("numItems", 0)),
                "parent_key": node.get("parentCollection") if node.get("parentCollection") else None,
                "children": [_build(c) for c in children_map.get(key, [])],
            }

        return {"data": [_build(r) for r in roots]}

    def show(self, key: str) -> ShowServiceResult:
        raw = self._api.collections()
        match = next((c for c in raw if c.get("key") == key), None)
        if match is None:
            from zotero_cli.models.errors import CollectionNotFoundError
            raise CollectionNotFoundError(f"Collection {key!r} not found")
        return {"data": match}

    def create(self, name: str, parent: str | None = None) -> MutationServiceResult:
        result = self._api.create_collection(name, parent)
        key = result.get("key", "")
        return {
            "data": {"successful": [{"index": 0, "key": key, "version": 0}], "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": [key]},
        }

    def delete(self, key: str) -> MutationServiceResult:
        self._api.delete_collection(key)
        return {
            "data": {"successful": [{"index": 0, "key": key, "version": 0}], "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": [key]},
        }

    def add_items(self, coll_key: str, item_keys: List[str]) -> MutationServiceResult:
        successful: list[Any] = []
        for idx, ik in enumerate(item_keys):
            self._api.add_to_collection(ik, coll_key)
            successful.append({"index": idx, "key": ik, "version": 0})
        return {
            "data": {"successful": successful, "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": [coll_key]},
        }

    def remove_items(self, coll_key: str, item_keys: List[str]) -> MutationServiceResult:
        successful: list[Any] = []
        for idx, ik in enumerate(item_keys):
            self._api.remove_from_collection(ik, coll_key)
            successful.append({"index": idx, "key": ik, "version": 0})
        return {
            "data": {"successful": successful, "unchanged": [], "failed": []},
            "meta_extra": {"affected_keys": [coll_key]},
        }
