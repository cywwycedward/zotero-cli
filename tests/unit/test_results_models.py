from __future__ import annotations

from zotero_cli.models.results import (
    CollectionNode,
    CollectionTreeServiceResult,
    ListServiceResult,
    MutationFailedItem,
    MutationServiceResult,
    MutationSuccessfulItem,
)


def test_list_service_result_required_fields() -> None:
    r: ListServiceResult = {
        "data": [{"key": "ABC"}],
        "meta_extra": {
            "count": 1,
            "total": 1,
            "limit": 100,
            "start": 0,
            "next_start": None,
        },
    }
    assert r["data"][0]["key"] == "ABC"
    assert r["meta_extra"]["count"] == 1


def test_mutation_failed_item_optional_context() -> None:
    f: MutationFailedItem = {"index": 0, "code": "E", "message": "m"}
    assert "context" not in f


def test_mutation_service_result_split() -> None:
    r: MutationServiceResult = {
        "data": {
            "successful": [{"index": 0, "key": "X", "version": 1}],
            "unchanged": [],
            "failed": [],
        },
        "meta_extra": {"affected_keys": ["X"]},
    }
    assert r["data"]["successful"][0]["key"] == "X"
    assert r["meta_extra"]["affected_keys"] == ["X"]


def test_mutation_successful_optional_data() -> None:
    s: MutationSuccessfulItem = {"index": 0, "key": "ABC", "version": 1}
    assert "data" not in s


def test_collection_node_recursive() -> None:
    child: CollectionNode = {
        "key": "C1",
        "name": "Child",
        "items_count": 5,
        "parent_key": "ROOT",
        "children": [],
    }
    root: CollectionNode = {
        "key": "ROOT",
        "name": "Root",
        "items_count": 10,
        "parent_key": None,
        "children": [child],
    }
    result: CollectionTreeServiceResult = {"data": [root]}
    assert result["data"][0]["children"][0]["key"] == "C1"
