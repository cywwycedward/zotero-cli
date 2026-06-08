from unittest.mock import MagicMock

import pytest

from zotero_cli.services.tag_service import TagService


@pytest.fixture
def svc() -> TagService:
    return TagService(MagicMock())


class TestList:
    def test_returns_data_with_key_field(self, svc) -> None:
        svc._api.tags.return_value = [{"tag": "nlp", "num_items": 5}]
        result = svc.list()
        assert result["data"][0]["key"] == "nlp"
        assert result["meta_extra"]["total"] == 1


class TestAdd:
    def test_adds_tag_to_item(self, svc) -> None:
        svc._api.item.return_value = {
            "key": "I1",
            "data": {"tags": [{"tag": "ai"}]},
        }
        result = svc.add("nlp", ["I1"])
        assert len(result["data"]["successful"]) == 1
        assert result["meta_extra"]["affected_keys"] == ["I1"]

    def test_already_tagged_unchanged(self, svc) -> None:
        svc._api.item.return_value = {
            "key": "I1",
            "data": {"tags": [{"tag": "nlp"}]},
        }
        result = svc.add("nlp", ["I1"])
        assert len(result["data"]["unchanged"]) == 1
        assert result["meta_extra"]["affected_keys"] == []


class TestRemove:
    def test_removes_tag_from_item(self, svc) -> None:
        svc._api.item.return_value = {
            "key": "I1",
            "data": {"tags": [{"tag": "nlp"}, {"tag": "ai"}]},
        }
        result = svc.remove("nlp", ["I1"])
        assert len(result["data"]["successful"]) == 1
        assert result["meta_extra"]["affected_keys"] == ["I1"]


class TestDelete:
    def test_deletes_tag(self, svc) -> None:
        result = svc.delete("nlp")
        svc._api.delete_tags.assert_called_once_with("nlp")
        assert len(result["data"]["successful"]) == 1
