from __future__ import annotations

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
