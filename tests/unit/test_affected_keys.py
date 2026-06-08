"""Parameterized tests for meta.affected_keys edge cases per design §7.2.1."""
from unittest.mock import MagicMock

import pytest

from zotero_cli.services.collection_service import CollectionService
from zotero_cli.services.item_service import ItemService
from zotero_cli.services.tag_service import TagService


@pytest.mark.parametrize("success,unch,fail,expected", [
    ([{"key": "A"}, {"key": "B"}], [], [], ["A", "B"]),
    ([{"key": "A"}], [{"key": "B"}], [{"key": "C"}], ["A"]),
    ([], [], [], []),
])
def test_item_create_affected_keys(success, unch, fail, expected) -> None:
    api = MagicMock()
    api.create_items.return_value = {
        "successful": success, "unchanged": unch, "failed": fail,
    }
    svc = ItemService(api)
    result = svc.create([{}])
    assert result["meta_extra"]["affected_keys"] == expected


def test_item_update_affected_keys() -> None:
    api = MagicMock()
    api.item.return_value = {"key": "ABC", "version": 5, "data": {"title": "Old"}}
    svc = ItemService(api)
    result = svc.update("ABC", patch={"title": "New"})
    assert result["meta_extra"]["affected_keys"] == ["ABC"]


def test_item_delete_affected_keys() -> None:
    api = MagicMock()
    api.item.return_value = {"key": "X"}
    svc = ItemService(api)
    result = svc.delete(["A", "B"])
    assert result["meta_extra"]["affected_keys"] == ["A", "B"]


def test_collection_create_affected_keys() -> None:
    api = MagicMock()
    api.create_collection.return_value = {"key": "CA"}
    svc = CollectionService(api)
    result = svc.create("New Coll")
    assert result["meta_extra"]["affected_keys"] == ["CA"]


def test_collection_add_items_only_collection_key() -> None:
    """§7.2.1: collections.add_items only has collection key in affected_keys."""
    api = MagicMock()
    svc = CollectionService(api)
    result = svc.add_items("COLL1", ["I1", "I2"])
    assert result["meta_extra"]["affected_keys"] == ["COLL1"]


def test_tag_add_affected_keys() -> None:
    api = MagicMock()
    api.item.side_effect = [
        {"key": "I1", "data": {"tags": []}},
        {"key": "I2", "data": {"tags": []}},
    ]
    svc = TagService(api)
    result = svc.add("nlp", ["I1", "I2"])
    assert result["meta_extra"]["affected_keys"] == ["I1", "I2"]


def test_tag_unchanged_not_in_affected_keys() -> None:
    """Existing tag → unchanged → not in affected_keys."""
    api = MagicMock()
    api.item.return_value = {"key": "I1", "data": {"tags": [{"tag": "nlp"}]}}
    svc = TagService(api)
    result = svc.add("nlp", ["I1"])
    assert result["meta_extra"]["affected_keys"] == []
    assert len(result["data"]["unchanged"]) == 1
