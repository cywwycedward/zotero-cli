from __future__ import annotations

import pytest
from pyzotero import zotero_errors as zerr

from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.errors import (
    ApiRateLimitError,
    ApiServerError,
    CLIError,
    FileNotFoundCLIError,
    InsufficientPermissionsError,
    InvalidApiKeyError,
    ItemNotFoundError,
    MissingRequiredArgError,
    MutuallyExclusiveArgsError,
    NetworkError,
    StorageQuotaExceededError,
)

# ── Task 2: ZoteroAPI init ────────────────────────────────────────────────


class TestZoteroAPIInit:
    def test_init_user_library(self, mocker) -> None:
        mock_zotero = mocker.patch("zotero_cli.adapters.zotero_api.Zotero")
        from zotero_cli.adapters.zotero_api import ZoteroAPI

        profile = ProfileConfig(api_key="k", library_id="123", library_type="user")
        ZoteroAPI(profile)
        mock_zotero.assert_called_once_with(
            library_id="123",
            library_type="user",
            api_key="k",
        )

    def test_init_group_library(self, mocker) -> None:
        mock_zotero = mocker.patch("zotero_cli.adapters.zotero_api.Zotero")
        from zotero_cli.adapters.zotero_api import ZoteroAPI

        profile = ProfileConfig(api_key="k", library_id="456", library_type="group")
        ZoteroAPI(profile)
        mock_zotero.assert_called_once_with(
            library_id="456",
            library_type="group",
            api_key="k",
        )

    def test_library_id_property(self, mocker) -> None:
        mocker.patch("pyzotero.zotero.Zotero")
        from zotero_cli.adapters.zotero_api import ZoteroAPI

        profile = ProfileConfig(api_key="k", library_id="123", library_type="user")
        api = ZoteroAPI(profile)
        assert api.library_id == "123"


# ── Task 3: _map_pyzotero_exception ────────────────────────────────────────


class TestMapPyzoteroException:
    def _map(self, exc: Exception) -> CLIError:
        from zotero_cli.adapters.zotero_api import _map_pyzotero_exception

        return _map_pyzotero_exception(exc)

    def test_file_does_not_exist(self) -> None:
        from pyzotero.zotero_errors import FileDoesNotExistError

        err = self._map(FileDoesNotExistError("file missing"))
        assert isinstance(err, FileNotFoundCLIError)
        assert err.code == "FILE_NOT_FOUND"

    def test_param_not_passed(self) -> None:
        from pyzotero.zotero_errors import ParamNotPassedError

        err = self._map(ParamNotPassedError("missing param"))
        assert isinstance(err, MissingRequiredArgError)
        assert err.code == "MISSING_REQUIRED_ARG"

    def test_unsupported_params(self) -> None:
        from pyzotero.zotero_errors import UnsupportedParamsError

        err = self._map(UnsupportedParamsError("bad params"))
        assert isinstance(err, MutuallyExclusiveArgsError)
        assert err.code == "MUTUALLY_EXCLUSIVE_ARGS"

    def test_too_many_requests(self) -> None:
        from pyzotero.zotero_errors import TooManyRequestsError

        err = self._map(TooManyRequestsError("rate limited"))
        assert isinstance(err, ApiRateLimitError)
        assert err.code == "API_RATE_LIMIT"

    def test_request_entity_too_large(self) -> None:
        from pyzotero.zotero_errors import RequestEntityTooLargeError

        err = self._map(RequestEntityTooLargeError("too large"))
        assert isinstance(err, StorageQuotaExceededError)
        assert err.code == "STORAGE_QUOTA_EXCEEDED"

    def test_precondition_failed(self) -> None:
        from pyzotero.zotero_errors import PreConditionFailedError

        err = self._map(PreConditionFailedError("precondition"))
        assert isinstance(err, ApiServerError)
        assert err.code == "API_SERVER_ERROR"

    def test_upload_error_network(self) -> None:
        from pyzotero.zotero_errors import UploadError

        err = self._map(UploadError("upload failed"))
        assert isinstance(err, NetworkError)
        assert err.code == "NETWORK_ERROR"

    def test_user_not_authorised_401(self) -> None:
        from pyzotero.zotero_errors import UserNotAuthorisedError

        err = self._map(UserNotAuthorisedError("unauthorized"))
        assert isinstance(err, InvalidApiKeyError)
        assert err.code == "INVALID_API_KEY"

    def test_user_not_authorised_403(self) -> None:
        from pyzotero.zotero_errors import UserNotAuthorisedError

        exc = UserNotAuthorisedError("forbidden")
        # pyzotero uses httpx.HTTPStatusError; we check message for 403
        # or just test the general auth error mapping
        err = self._map(exc)
        assert isinstance(err, (InvalidApiKeyError, InsufficientPermissionsError))

    def test_resource_not_found_404_item(self) -> None:
        from pyzotero.zotero_errors import ResourceNotFoundError

        err = self._map(ResourceNotFoundError("not found"))
        assert isinstance(err, ItemNotFoundError)
        assert err.code == "ITEM_NOT_FOUND"

    def test_translated_error_carries_cause(self) -> None:
        from pyzotero.zotero_errors import TooManyRequestsError

        orig = TooManyRequestsError("rate limited")
        err = self._map(orig)
        assert err.cause is orig

    def test_unmapped_error_falls_back_to_cli_error(self) -> None:
        from pyzotero.zotero_errors import PyZoteroError

        err = self._map(PyZoteroError("generic"))
        assert type(err) is CLIError
        assert "unmapped" in err.message.lower()


# ── Task 4: _select_backend ────────────────────────────────────────────────


class TestSelectBackend:
    def test_no_webdav_returns_zfs(self) -> None:
        from zotero_cli.adapters.zotero_api import _select_backend

        profile = ProfileConfig(api_key="k", library_id="1", library_type="user")
        assert _select_backend(profile) == "zfs"

    def test_with_webdav_returns_webdav(self) -> None:
        from zotero_cli.adapters.zotero_api import _select_backend

        profile = ProfileConfig(
            api_key="k",
            library_id="1",
            library_type="user",
            webdav={"url": "https://x", "username": "u", "password": "p"},
        )  # type: ignore[call-arg]
        assert _select_backend(profile) == "webdav"


# ── _normalize_batch_result (real Zotero API format) ─────────────────────


class TestNormalizeBatchResult:
    """Test against real Zotero Web API response format.

    Zotero returns {"success": {"0": "KEY"}, "unchanged": {}, "failed": {}},
    NOT {"successful": [...]}.
    """

    def _normalize(self, result, payloads):
        from zotero_cli.adapters.zotero_api import _normalize_batch_result

        return _normalize_batch_result(result, payloads)

    def test_single_create_success(self) -> None:
        api_response = {
            "success": {"0": "ABCD1234"},
            "unchanged": {},
            "failed": {},
        }
        payloads = [{"itemType": "journalArticle", "title": "Test"}]
        result = self._normalize(api_response, payloads)
        assert len(result["successful"]) == 1
        assert result["successful"][0]["key"] == "ABCD1234"
        assert result["successful"][0]["index"] == 0

    def test_multi_create_success(self) -> None:
        api_response = {
            "success": {"0": "KEY1", "1": "KEY2"},
            "unchanged": {},
            "failed": {},
        }
        payloads = [
            {"itemType": "journalArticle", "title": "A"},
            {"itemType": "note", "title": "B"},
        ]
        result = self._normalize(api_response, payloads)
        assert len(result["successful"]) == 2
        assert result["successful"][0]["key"] == "KEY1"
        assert result["successful"][1]["key"] == "KEY2"

    def test_partial_failure(self) -> None:
        api_response = {
            "success": {"0": "KEY1"},
            "unchanged": {},
            "failed": {"1": {"code": 400, "message": "Bad item type"}},
        }
        payloads = [
            {"itemType": "journalArticle", "title": "Good"},
            {"itemType": "badType", "title": "Bad"},
        ]
        result = self._normalize(api_response, payloads)
        assert len(result["successful"]) == 1
        assert len(result["failed"]) == 1
        assert result["successful"][0]["key"] == "KEY1"

    def test_all_failed(self) -> None:
        api_response = {
            "success": {},
            "unchanged": {},
            "failed": {"0": {"code": 400, "message": "Invalid"}},
        }
        payloads = [{"itemType": "bad"}]
        result = self._normalize(api_response, payloads)
        assert len(result["successful"]) == 0
        assert len(result["failed"]) == 1


# ── Helper fixture ────────────────────────────────────────────────────────


def _make_api(mocker):
    """Return (api, mock_zot) where mock_zot is the mocked Zotero instance."""
    mock_zotero_cls = mocker.patch("zotero_cli.adapters.zotero_api.Zotero")
    mock_zot = mock_zotero_cls.return_value
    from zotero_cli.adapters.zotero_api import ZoteroAPI

    profile = ProfileConfig(api_key="k", library_id="123", library_type="user")
    api = ZoteroAPI(profile)
    return api, mock_zot


# ── Read methods ──────────────────────────────────────────────────────────


class TestZoteroAPIReadMethods:
    def test_items_top_success_returns_list(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.top.return_value = [{"key": "A", "data": {"title": "T"}}]
        result = api.items_top()
        assert result == [{"key": "A", "data": {"title": "T"}}]
        mock_zot.top.assert_called_once()

    def test_items_top_with_collection_uses_collection_items_top(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.collection_items_top.return_value = []
        api.items_top(collection="COL1")
        mock_zot.collection_items_top.assert_called_once()
        assert mock_zot.collection_items_top.call_args[0][0] == "COL1"
        mock_zot.top.assert_not_called()

    def test_items_top_with_tag_passes_filter(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.top.return_value = []
        api.items_top(tag="mytag")
        _, kwargs = mock_zot.top.call_args
        assert kwargs["tag"] == "mytag"

    def test_items_top_error_raises_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.top.side_effect = zerr.TooManyRequestsError("rate limited")
        with pytest.raises(ApiRateLimitError):
            api.items_top()

    def test_items_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = [{"key": "B"}]
        result = api.items()
        assert result == [{"key": "B"}]
        mock_zot.items.assert_called_once()

    def test_item_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.return_value = {"key": "X", "data": {"title": "Found"}}
        result = api.item("X")
        assert result["key"] == "X"
        mock_zot.item.assert_called_once_with("X")

    def test_item_not_found_raises_item_not_found_error(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.side_effect = zerr.ResourceNotFoundError("not found")
        with pytest.raises(ItemNotFoundError, match="Item 'MISSING' not found"):
            api.item("MISSING")

    def test_item_generic_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.side_effect = zerr.TooManyRequestsError("rate limited")
        with pytest.raises(ApiRateLimitError):
            api.item("X")

    def test_search_items_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = [{"key": "S1"}]
        result = api.search_items("test query")
        assert result == [{"key": "S1"}]
        _, kwargs = mock_zot.items.call_args
        assert kwargs["q"] == "test query"

    def test_top_count_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.num_items.return_value = 42
        assert api.top_count() == 42

    def test_count_items_with_collection(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.num_collectionitems.return_value = 10
        assert api.count_items(collection="COL1") == 10
        mock_zot.num_collectionitems.assert_called_once_with("COL1")

    def test_count_items_with_tag(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.num_items.return_value = 5
        assert api.count_items(tag="urgent") == 5
        mock_zot.num_items.assert_called_once()

    def test_count_items_default_delegates_to_top_count(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.num_items.return_value = 99
        assert api.count_items() == 99

    def test_last_modified_version_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.last_modified_version.return_value = 7
        assert api.last_modified_version() == 7


# ── Write methods ─────────────────────────────────────────────────────────


class TestZoteroAPIWriteMethods:
    def test_create_items_normalizes_result(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.create_items.return_value = {
            "success": {"0": "NEW1"},
            "unchanged": {},
            "failed": {},
        }
        payloads = [{"itemType": "journalArticle", "title": "A"}]
        result = api.create_items(payloads)
        assert len(result["successful"]) == 1
        assert result["successful"][0]["key"] == "NEW1"

    def test_update_item_returns_true(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.update_item.return_value = None
        item = {"key": "X", "version": 1, "data": {}}
        assert api.update_item(item) is True
        mock_zot.update_item.assert_called_once_with(item)

    def test_update_item_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.update_item.side_effect = zerr.PreConditionFailedError("conflict")
        with pytest.raises(ApiServerError):
            api.update_item({"key": "X"})

    def test_delete_item_returns_true(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.delete_item.return_value = None
        item = {"key": "X", "version": 1}
        assert api.delete_item(item) is True
        mock_zot.delete_item.assert_called_once_with(item)


# ── Attachment methods ────────────────────────────────────────────────────


class TestZoteroAPIAttachmentMethods:
    def test_attachment_simple_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.attachment_simple.return_value = {"success": "ok"}
        result = api.attachment_simple(["/tmp/a.pdf"], parentid="P1")
        assert result == {"success": "ok"}
        mock_zot.attachment_simple.assert_called_once_with(["/tmp/a.pdf"], parentid="P1")

    def test_attachment_both_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.attachment_both.return_value = {"success": "ok"}
        files = [("/tmp/a.pdf", "Title A")]
        result = api.attachment_both(files, parentid="P1")
        assert result == {"success": "ok"}
        mock_zot.attachment_both.assert_called_once_with(files, parentid="P1")

    def test_upload_attachments_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.upload_attachments.return_value = {"success": "ok"}
        attachments = [{"path": "/tmp/a.pdf"}]
        result = api.upload_attachments(attachments, parentid="P2")
        assert result == {"success": "ok"}
        mock_zot.upload_attachments.assert_called_once_with(attachments, parentid="P2")

    def test_item_template_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item_template.return_value = {"itemType": "note", "note": ""}
        result = api.item_template("note", "imported_file")
        assert result == {"itemType": "note", "note": ""}
        mock_zot.item_template.assert_called_once_with("note", "imported_file")


# ── Collection methods ────────────────────────────────────────────────────


class TestZoteroAPICollectionMethods:
    def test_collections_returns_parsed(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.collections.return_value = [{"key": "C1", "data": {"name": "Col"}}]
        result = api.collections()
        assert result == [{"key": "C1", "data": {"name": "Col"}}]

    def test_create_collection_basic(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.create_collection.return_value = {
            "success": {"0": "NEW"},
            "unchanged": {},
            "failed": {},
        }
        result = api.create_collection("My Collection")
        assert result == {"key": "NEW"}
        mock_zot.create_collection.assert_called_once_with([{"name": "My Collection"}])

    def test_create_collection_with_parent(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.create_collection.return_value = {
            "success": {"0": "CHILD"},
            "unchanged": {},
            "failed": {},
        }
        result = api.create_collection("Sub", parent="PARENT1")
        assert result == {"key": "CHILD"}
        mock_zot.create_collection.assert_called_once_with(
            [{"name": "Sub", "parentCollection": "PARENT1"}]
        )

    def test_create_collection_returns_normalized_key(self, mocker) -> None:
        """create_collection must extract key from pyzotero batch result."""
        api, mock_zot = _make_api(mocker)
        mock_zot.create_collection.return_value = {
            "success": {"0": "NEWCOLL"},
            "unchanged": {},
            "failed": {},
        }
        result = api.create_collection("Test Collection")
        assert result["key"] == "NEWCOLL"

    def test_create_collection_failed_raises(self, mocker) -> None:
        """create_collection must raise CLIError when batch result has no success."""
        api, mock_zot = _make_api(mocker)
        mock_zot.create_collection.return_value = {
            "success": {},
            "unchanged": {},
            "failed": {"0": {"code": 400, "message": "Invalid"}},
        }
        with pytest.raises(CLIError, match="Collection creation failed"):
            api.create_collection("Bad Coll")

    def test_delete_collection_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.collections.return_value = [
            {"key": "C1", "data": {"name": "Col"}},
        ]
        mock_zot.delete_collection.return_value = None
        assert api.delete_collection("C1") is True
        mock_zot.delete_collection.assert_called_once_with({"key": "C1", "data": {"name": "Col"}})

    def test_delete_collection_not_found_raises(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.collections.return_value = []
        with pytest.raises(ItemNotFoundError, match="Collection 'MISSING' not found"):
            api.delete_collection("MISSING")

    def test_add_to_collection_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.return_value = {"key": "I1", "data": {"title": "Item"}}
        mock_zot.addto_collection.return_value = None
        assert api.add_to_collection("I1", "C1") is True
        mock_zot.addto_collection.assert_called_once_with(
            "C1", {"key": "I1", "data": {"title": "Item"}}
        )

    def test_remove_from_collection_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.return_value = {"key": "I1", "data": {"title": "Item"}}
        mock_zot.deletefrom_collection.return_value = None
        assert api.remove_from_collection("I1", "C1") is True
        mock_zot.deletefrom_collection.assert_called_once_with(
            "C1", {"key": "I1", "data": {"title": "Item"}}
        )


# ── Tag methods ───────────────────────────────────────────────────────────


class TestZoteroAPITagMethods:
    def test_tags_returns_parsed(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.tags.return_value = [{"tag": "physics"}, {"tag": "math"}]
        result = api.tags()
        assert result == [{"tag": "physics"}, {"tag": "math"}]

    def test_delete_tags_success(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.delete_tags.return_value = None
        assert api.delete_tags("a", "b") is True
        mock_zot.delete_tags.assert_called_once_with("a", "b")


# ── Export ────────────────────────────────────────────────────────────────


class TestZoteroAPIExport:
    def test_export_items_str_result_encoded(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = "bibtex content"
        result = api.export_items("bibtex")
        assert result == b"bibtex content"

    def test_export_items_bytes_result_passthrough(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = b"\x89PNG raw"
        result = api.export_items("ris")
        assert result == b"\x89PNG raw"

    def test_export_items_other_result_str_encoded(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = 12345
        result = api.export_items("csljson")
        assert result == b"12345"

    def test_export_items_with_collection_filter(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = ""
        api.export_items("bibtex", collection="C1")
        _, kwargs = mock_zot.items.call_args
        assert kwargs["collection"] == "C1"

    def test_export_items_with_tag_filter(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = ""
        api.export_items("bibtex", tag="urgent")
        _, kwargs = mock_zot.items.call_args
        assert kwargs["tag"] == "urgent"

    def test_export_items_bibdatabase_serialized(self, mocker) -> None:
        """bibtex: pyzotero returns BibDatabase; must serialize to BibTeX text."""
        from bibtexparser.bibdatabase import BibDatabase

        api, mock_zot = _make_api(mocker)
        bib_db = BibDatabase()
        bib_db.entries = [{"ID": "key1", "ENTRYTYPE": "article", "title": "Test Paper"}]
        mock_zot.items.return_value = bib_db
        result = api.export_items("bibtex")
        assert b"key1" in result
        assert b"Test Paper" in result
        assert b"BibDatabase" not in result

    def test_export_items_list_of_dict_as_json(self, mocker) -> None:
        """csljson: pyzotero returns list[dict]; must serialize as JSON."""
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = [{"id": "1", "type": "article-journal"}]
        result = api.export_items("csljson")
        import json

        parsed = json.loads(result)
        assert parsed == [{"id": "1", "type": "article-journal"}]

    def test_export_items_list_of_str_joined(self, mocker) -> None:
        """Fallback: list[str] items joined with newlines."""
        api, mock_zot = _make_api(mocker)
        mock_zot.items.return_value = ["entry one", "entry two"]
        result = api.export_items("wikipedia")
        assert result == b"entry one\nentry two"

    def test_export_items_json_decode_error_mapped(self, mocker) -> None:
        """Non-PyZoteroError (e.g. JSONDecodeError from RIS) must be caught and mapped."""
        import json as _json

        api, mock_zot = _make_api(mocker)
        mock_zot.items.side_effect = _json.JSONDecodeError("bad", "", 0)
        with pytest.raises(CLIError, match="Export failed"):
            api.export_items("ris")


# ── _pyzotero_parse helper ────────────────────────────────────────────────


class TestPyzoteroParseHelper:
    def test_str_input_json_decoded(self) -> None:
        from zotero_cli.adapters.zotero_api import _pyzotero_parse

        result = _pyzotero_parse('[{"key": "A"}]')
        assert result == [{"key": "A"}]

    def test_list_input_passthrough(self) -> None:
        from zotero_cli.adapters.zotero_api import _pyzotero_parse

        data = [{"key": "B"}]
        result = _pyzotero_parse(data)
        assert result is data


# ── Exception mapping edge cases ──────────────────────────────────────────


class TestExceptionMappingEdgeCases:
    def _map(self, exc: Exception):
        from zotero_cli.adapters.zotero_api import _map_pyzotero_exception

        return _map_pyzotero_exception(exc)

    def test_upload_error_timeout_maps_to_api_timeout(self) -> None:
        from zotero_cli.adapters.zotero_api import ApiTimeoutError

        err = self._map(zerr.UploadError("connection timeout exceeded"))
        assert isinstance(err, ApiTimeoutError)
        assert err.code == "API_TIMEOUT"

    def test_user_not_authorised_403_maps_to_insufficient_permissions(self) -> None:
        err = self._map(zerr.UserNotAuthorisedError("403 Forbidden"))
        assert isinstance(err, InsufficientPermissionsError)
        assert err.code == "INSUFFICIENT_PERMISSIONS"


# ── Error paths in wrapper methods (representative coverage) ─────────────


class TestZoteroAPIMethodErrors:
    """Cover except branches in wrapper methods not already tested above."""

    def test_items_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.items()

    def test_search_items_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.search_items("q")

    def test_count_items_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.num_items.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.count_items()

    def test_last_modified_version_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.last_modified_version.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.last_modified_version()

    def test_create_items_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.create_items.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.create_items([{}])

    def test_delete_item_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.delete_item.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.delete_item({"key": "X"})

    def test_attachment_simple_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.attachment_simple.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.attachment_simple(["/tmp/a.pdf"])

    def test_collections_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.collections.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.collections()

    def test_create_collection_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.create_collection.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.create_collection("C")

    def test_delete_collection_pyzotero_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.collections.return_value = [{"key": "C1", "data": {}}]
        mock_zot.delete_collection.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.delete_collection("C1")

    def test_tags_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.tags.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.tags()

    def test_delete_tags_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.delete_tags.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.delete_tags("a")

    def test_export_items_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.items.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.export_items("bibtex")

    def test_add_to_collection_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.return_value = {"key": "I1"}
        mock_zot.addto_collection.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.add_to_collection("I1", "C1")

    def test_remove_from_collection_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item.return_value = {"key": "I1"}
        mock_zot.deletefrom_collection.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.remove_from_collection("I1", "C1")

    def test_attachment_both_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.attachment_both.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.attachment_both([("t", "/tmp/a.pdf")])

    def test_upload_attachments_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.upload_attachments.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.upload_attachments([{}])

    def test_item_template_error_mapped(self, mocker) -> None:
        api, mock_zot = _make_api(mocker)
        mock_zot.item_template.side_effect = zerr.PyZoteroError("fail")
        with pytest.raises(CLIError):
            api.item_template("note")


# ── Issue #4: collection routing for items_top ────────────────────────────


class TestItemsTopCollectionRouting:
    def test_collection_uses_collection_items_top(self, mocker) -> None:
        """When collection is given, must call collection_items_top, not top."""
        mock_zotero = mocker.patch("zotero_cli.adapters.zotero_api.Zotero")
        from zotero_cli.adapters.zotero_api import ZoteroAPI
        from zotero_cli.models.config import ProfileConfig

        profile = ProfileConfig(api_key="k", library_id="123", library_type="user")
        api = ZoteroAPI(profile)
        instance = mock_zotero.return_value
        instance.collection_items_top.return_value = [{"key": "A"}]

        result = api.items_top(collection="WUHL3RII")

        assert result == [{"key": "A"}]
        instance.collection_items_top.assert_called_once()
        call_args = instance.collection_items_top.call_args
        assert call_args[0][0] == "WUHL3RII"
        instance.top.assert_not_called()

    def test_no_collection_uses_top(self, mocker) -> None:
        """Without collection, must call top()."""
        mock_zotero = mocker.patch("zotero_cli.adapters.zotero_api.Zotero")
        from zotero_cli.adapters.zotero_api import ZoteroAPI
        from zotero_cli.models.config import ProfileConfig

        profile = ProfileConfig(api_key="k", library_id="123", library_type="user")
        api = ZoteroAPI(profile)
        instance = mock_zotero.return_value
        instance.top.return_value = [{"key": "B"}]

        result = api.items_top()

        assert result == [{"key": "B"}]
        instance.top.assert_called_once()
        instance.collection_items_top.assert_not_called()
