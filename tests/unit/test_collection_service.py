from unittest.mock import MagicMock

import pytest

from zotero_cli.services.collection_service import CollectionService


@pytest.fixture
def svc() -> CollectionService:
    return CollectionService(MagicMock())


class TestList:
    def test_builds_tree_from_flat(self, svc) -> None:
        svc._api.collections.return_value = [
            {"key": "R", "data": {"name": "Root"}, "meta": {"numItems": 10}},
            {"key": "C1", "data": {"name": "Child1"}, "parentCollection": "R", "meta": {"numItems": 5}},
            {"key": "C2", "data": {"name": "Child2"}, "parentCollection": "R", "meta": {"numItems": 3}},
        ]
        result = svc.list()
        root = result["data"][0]
        assert root["key"] == "R"
        assert root["name"] == "Root"
        assert len(root["children"]) == 2

    def test_orphans_become_roots(self, svc) -> None:
        svc._api.collections.return_value = [
            {"key": "A", "data": {"name": "A"}, "meta": {"numItems": 1}},
            {"key": "B", "data": {"name": "B"}, "parentCollection": "NONEXIST", "meta": {"numItems": 2}},
        ]
        result = svc.list()
        assert len(result["data"]) == 2


class TestCreate:
    def test_returns_affected_key(self, svc) -> None:
        svc._api.create_collection.return_value = {"key": "NEW"}
        result = svc.create("My Coll")
        assert result["meta_extra"]["affected_keys"] == ["NEW"]


class TestAddItems:
    def test_affected_keys_is_collection_key(self, svc) -> None:
        result = svc.add_items("COLL1", ["I1", "I2"])
        assert result["meta_extra"]["affected_keys"] == ["COLL1"]
        assert len(result["data"]["successful"]) == 2
