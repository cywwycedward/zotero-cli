from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zotero_cli.models.errors import InvalidFieldError, ItemNotFoundError
from zotero_cli.services.item_service import ItemService


@pytest.fixture
def mock_api() -> MagicMock:
    return MagicMock()


@pytest.fixture
def svc(mock_api: MagicMock) -> ItemService:
    return ItemService(mock_api)


class TestList:
    def test_returns_data_with_meta(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [{"key": "ABC", "title": "Paper"}]
        mock_api.count_items.return_value = 1
        mock_api.library_id = "12345"
        mock_api.last_modified_version.return_value = 5678

        result = svc.list(limit=50, start=0)
        assert result["data"] == [{"key": "ABC", "title": "Paper"}]
        assert result["meta_extra"]["count"] == 1
        assert result["meta_extra"]["total"] == 1
        assert result["meta_extra"]["limit"] == 50
        assert result["meta_extra"]["start"] == 0
        assert result["meta_extra"]["library_id"] == "12345"

    def test_passes_collection_filter(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = []
        mock_api.count_items.return_value = 0
        mock_api.library_id = "123"
        mock_api.last_modified_version.return_value = 1

        svc.list(collection="COLL1")
        mock_api.items_top.assert_called_once_with(
            limit=100,
            start=0,
            collection="COLL1",
            tag=None,
        )


class TestSearch:
    def test_passes_query(self, svc, mock_api) -> None:
        mock_api.search_items.return_value = [{"key": "X"}]
        mock_api.library_id = "123"
        mock_api.last_modified_version.return_value = 1

        result = svc.search("transformer", limit=10)
        mock_api.search_items.assert_called_once_with("transformer", limit=10, start=0)
        assert result["data"] == [{"key": "X"}]


class TestShow:
    def test_returns_item(self, svc, mock_api) -> None:
        mock_api.item.return_value = {"key": "ABC"}
        result = svc.show("ABC")
        assert result["data"] == {"key": "ABC"}

    def test_404_propagates(self, svc, mock_api) -> None:
        mock_api.item.side_effect = ItemNotFoundError("nope")
        with pytest.raises(ItemNotFoundError):
            svc.show("NOPE")

    def test_flattens_nested_data(self, svc, mock_api) -> None:
        """show() must flatten item['data'] to top level like list/search do."""
        mock_api.item.return_value = {
            "key": "ABC123",
            "version": 42,
            "data": {
                "key": "ABC123",
                "title": "Attention Is All You Need",
                "itemType": "journalArticle",
                "creators": [{"firstName": "A", "lastName": "V"}],
                "date": "2017",
                "tags": [{"tag": "transformers"}],
            },
        }
        result = svc.show("ABC123")
        data = result["data"]
        assert data["title"] == "Attention Is All You Need"
        assert data["key"] == "ABC123"
        assert data["itemType"] == "journalArticle"
        assert data["creators"] == [{"firstName": "A", "lastName": "V"}]

    def test_already_flat_passthrough(self, svc, mock_api) -> None:
        """If item has no nested 'data', return as-is."""
        mock_api.item.return_value = {"key": "X", "title": "Flat"}
        result = svc.show("X")
        assert result["data"]["title"] == "Flat"


class TestCreate:
    def test_single_success(self, svc, mock_api) -> None:
        mock_api.create_items.return_value = {
            "successful": [{"index": 0, "key": "NEW", "version": 1}],
            "unchanged": [],
            "failed": [],
        }
        result = svc.create([{"itemType": "journalArticle", "title": "T"}])
        assert result["meta_extra"]["affected_keys"] == ["NEW"]
        assert len(result["data"]["successful"]) == 1


class TestCreateSingle:
    def test_returns_successful_item(self, svc, mock_api) -> None:
        mock_api.create_items.return_value = {
            "successful": [{"index": 0, "key": "NEW", "version": 1}],
            "unchanged": [],
            "failed": [],
        }
        item = svc.create_single({"itemType": "journalArticle"})
        assert item["key"] == "NEW"


class TestUpdate:
    def test_merges_patch(self, svc, mock_api) -> None:
        mock_api.item.return_value = {
            "key": "ABC",
            "version": 5,
            "data": {"title": "Old", "itemType": "journalArticle"},
        }
        result = svc.update("ABC", patch={"title": "New"})
        mock_api.update_item.assert_called_once()
        updated = mock_api.update_item.call_args[0][0]
        assert updated["data"]["title"] == "New"
        assert result["meta_extra"]["affected_keys"] == ["ABC"]

    def test_add_tags_merged_into_existing_tags(self, svc, mock_api) -> None:
        """add_tags must merge with existing tags and not appear in API payload."""
        mock_api.item.return_value = {
            "key": "ABC",
            "version": 5,
            "data": {
                "title": "Paper",
                "itemType": "journalArticle",
                "tags": [{"tag": "existing"}],
            },
        }
        svc.update("ABC", patch={"add_tags": ["new-tag"]})
        mock_api.update_item.assert_called_once()
        sent = mock_api.update_item.call_args[0][0]
        assert "add_tags" not in sent["data"]
        tag_values = {t["tag"] for t in sent["data"]["tags"]}
        assert tag_values == {"existing", "new-tag"}

    def test_add_tags_when_no_existing_tags(self, svc, mock_api) -> None:
        """add_tags works when item has no existing tags."""
        mock_api.item.return_value = {
            "key": "ABC",
            "version": 5,
            "data": {"title": "Paper", "itemType": "journalArticle", "tags": []},
        }
        svc.update("ABC", patch={"add_tags": ["tag-a", "tag-b"]})
        sent = mock_api.update_item.call_args[0][0]
        assert "add_tags" not in sent["data"]
        tag_values = {t["tag"] for t in sent["data"]["tags"]}
        assert tag_values == {"tag-a", "tag-b"}

    def test_add_tags_deduplicates(self, svc, mock_api) -> None:
        """add_tags does not create duplicate tag entries."""
        mock_api.item.return_value = {
            "key": "ABC",
            "version": 5,
            "data": {
                "title": "Paper",
                "itemType": "journalArticle",
                "tags": [{"tag": "already"}],
            },
        }
        svc.update("ABC", patch={"add_tags": ["already", "fresh"]})
        sent = mock_api.update_item.call_args[0][0]
        tag_values = [t["tag"] for t in sent["data"]["tags"]]
        assert sorted(tag_values) == ["already", "fresh"]

    def test_add_tags_does_not_mutate_input_patch(self, svc, mock_api) -> None:
        """update() must not mutate the caller's patch dict."""
        mock_api.item.return_value = {
            "key": "ABC",
            "version": 5,
            "data": {"title": "Paper", "itemType": "journalArticle", "tags": []},
        }
        patch = {"title": "New Title", "add_tags": ["t1"]}
        patch_before = dict(patch)
        svc.update("ABC", patch=patch)
        assert patch == patch_before


class TestDelete:
    def test_multi_keys(self, svc, mock_api) -> None:
        mock_api.item.return_value = {"key": "X"}
        result = svc.delete(["A", "B"])
        assert len(result["data"]["successful"]) == 2
        assert result["meta_extra"]["affected_keys"] == ["A", "B"]


class TestFlattenItem:
    def test_nested_pyzotero_response_is_flattened(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [
            {
                "key": "ABC",
                "version": 5,
                "data": {
                    "key": "ABC",
                    "title": "Nested Paper",
                    "itemType": "journalArticle",
                    "creators": [{"firstName": "A", "lastName": "B"}],
                    "date": "2026",
                    "tags": [{"tag": "test"}],
                },
            }
        ]
        mock_api.count_items.return_value = 1
        mock_api.library_id = "123"
        mock_api.last_modified_version.return_value = 1

        result = svc.list(limit=10)
        item = result["data"][0]
        assert item["key"] == "ABC"
        assert item["title"] == "Nested Paper"
        assert item["itemType"] == "journalArticle"
        assert item["creators"] == [{"firstName": "A", "lastName": "B"}]

    def test_flat_dict_passes_through(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [{"key": "X", "title": "Flat"}]
        mock_api.count_items.return_value = 1
        mock_api.library_id = "123"
        mock_api.last_modified_version.return_value = 1

        result = svc.list()
        item = result["data"][0]
        assert item["key"] == "X"
        assert item["title"] == "Flat"

    def test_search_also_flattens(self, svc, mock_api) -> None:
        mock_api.search_items.return_value = [
            {
                "key": "S1",
                "data": {"key": "S1", "title": "Search Result"},
            }
        ]
        mock_api.library_id = "123"
        mock_api.last_modified_version.return_value = 1

        result = svc.search("query")
        assert result["data"][0]["title"] == "Search Result"


class TestFindByDoi:
    TARGET = "10.1038/s41586-020-2649-2"

    def _item(self, key: str, doi: object) -> dict[str, object]:
        return {"key": key, "data": {"key": key, "title": f"Paper {key}", "DOI": doi}}

    def test_bare_doi_matches(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [self._item("M1", self.TARGET)]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert [i["key"] for i in result["data"]] == ["M1"]
        assert result["meta_extra"]["count"] == 1
        assert result["meta_extra"]["normalized_doi"] == self.TARGET

    def test_doi_prefix_input_matches(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [self._item("M1", self.TARGET)]
        mock_api.library_id = "123"
        result = svc.find_by_doi(f"doi:{self.TARGET}")
        assert [i["key"] for i in result["data"]] == ["M1"]
        assert result["meta_extra"]["normalized_doi"] == self.TARGET

    def test_url_input_matches(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [self._item("M1", self.TARGET)]
        mock_api.library_id = "123"
        result = svc.find_by_doi(f"https://doi.org/{self.TARGET}")
        assert [i["key"] for i in result["data"]] == ["M1"]

    def test_case_insensitive_match(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [self._item("M1", "10.1038/S41586-020-2649-2")]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert [i["key"] for i in result["data"]] == ["M1"]

    def test_item_without_doi_skipped(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [
            {"key": "NO", "data": {"key": "NO", "title": "No DOI"}},
            self._item("M1", self.TARGET),
        ]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert [i["key"] for i in result["data"]] == ["M1"]

    def test_dirty_or_unnormalizable_doi_skipped(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [
            self._item("EMPTY", ""),
            self._item("PREFIXONLY", "doi:"),
            self._item("NONE", None),
            self._item("NUM", 12345),
            self._item("M1", self.TARGET),
        ]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert [i["key"] for i in result["data"]] == ["M1"]

    def test_collection_scopes_fetch(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = []
        mock_api.library_id = "123"
        svc.find_by_doi(self.TARGET, collection="C1")
        mock_api.items_top.assert_called_once_with(limit=100, start=0, collection="C1")

    def test_paginates_until_short_page(self, svc, mock_api) -> None:
        page1 = [self._item(f"K{i}", "10.0000/none") for i in range(100)]
        page2 = [self._item("M1", self.TARGET)]
        mock_api.items_top.side_effect = [page1, page2]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert [i["key"] for i in result["data"]] == ["M1"]
        assert mock_api.items_top.call_count == 2
        assert mock_api.items_top.call_args_list[0].kwargs["start"] == 0
        assert mock_api.items_top.call_args_list[1].kwargs["start"] == 100

    def test_paginates_until_empty_page(self, svc, mock_api) -> None:
        page1 = [self._item(f"K{i}", "10.0000/none") for i in range(100)]
        mock_api.items_top.side_effect = [page1, []]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert result["data"] == []
        assert result["meta_extra"]["count"] == 0
        assert mock_api.items_top.call_count == 2

    def test_not_found_returns_empty(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [self._item("X", "10.0000/none")]
        mock_api.library_id = "123"
        result = svc.find_by_doi(self.TARGET)
        assert result["data"] == []
        assert result["meta_extra"]["count"] == 0
        assert result["meta_extra"]["total"] == 0

    def test_invalid_doi_raises(self, svc, mock_api) -> None:
        with pytest.raises(InvalidFieldError):
            svc.find_by_doi("not-a-doi")

    def test_meta_fields(self, svc, mock_api) -> None:
        mock_api.items_top.return_value = [self._item("M1", self.TARGET)]
        mock_api.library_id = "LIB9"
        raw = f"https://doi.org/{self.TARGET}"
        result = svc.find_by_doi(raw, collection="C1")
        meta = result["meta_extra"]
        assert meta["query_doi"] == raw
        assert meta["normalized_doi"] == self.TARGET
        assert meta["collection"] == "C1"
        assert meta["library_id"] == "LIB9"
        assert meta["count"] == 1
        assert meta["total"] == 1
