from __future__ import annotations

import pytest

from zotero_cli.models.errors import (
    # user_error
    ApiRateLimitError,
    ApiServerError,
    ApiTimeoutError,
    AuditLogWriteFailedError,
    CLIError,
    CollectionNotFoundError,
    ConfigInvalidError,
    ConfigNotFoundError,
    FeedNotFoundError,
    FileNotFoundCLIError,
    InsufficientPermissionsError,
    InvalidApiKeyError,
    InvalidDateFormatError,
    InvalidFieldError,
    InvalidItemTypeError,
    InvalidProfileError,
    ItemNotFoundError,
    Md5MismatchError,
    MissingRequiredArgError,
    MutuallyExclusiveArgsError,
    NetworkError,
    SqliteLockedError,
    SqliteNotFoundError,
    SqliteSchemaIncompatibleError,
    StorageQuotaExceededError,
    TagNotFoundError,
    UnsupportedLibraryTypeError,
    UsageError,
    WebdavAuthFailedError,
    WebdavConnectionError,
    WebdavFileExistsError,
    WebdavPropInvalidError,
    WebdavTimeoutError,
    from_code,
)
from zotero_cli.utils.exit_codes import EXIT_USER_ERROR


class TestCLIErrorBase:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(CLIError, Exception)

    def test_default_attrs(self) -> None:
        err = CLIError("something went wrong")
        assert err.message == "something went wrong"
        assert err.code == "GENERIC"
        assert err.category == "user_error"
        assert err.exit_code == EXIT_USER_ERROR
        assert err.hint is None
        assert err.context == {}
        assert err.cause is None

    def test_keyword_overrides(self) -> None:
        cause = ValueError("inner")
        err = CLIError(
            "msg",
            hint="try X",
            context={"key": "value"},
            cause=cause,
        )
        assert err.hint == "try X"
        assert err.context == {"key": "value"}
        assert err.cause is cause

    def test_str_returns_message(self) -> None:
        err = CLIError("readable message")
        assert str(err) == "readable message"

    def test_subclass_inherits_class_attrs(self) -> None:
        class FakeAuthError(CLIError):
            code = "FAKE_AUTH"
            category = "auth_error"
            exit_code = 3

        err = FakeAuthError("nope")
        assert err.code == "FAKE_AUTH"
        assert err.category == "auth_error"
        assert err.exit_code == 3


USER_ERROR_CASES = [
    (ItemNotFoundError, "ITEM_NOT_FOUND"),
    (CollectionNotFoundError, "COLLECTION_NOT_FOUND"),
    (TagNotFoundError, "TAG_NOT_FOUND"),
    (FeedNotFoundError, "FEED_NOT_FOUND"),
    (InvalidItemTypeError, "INVALID_ITEM_TYPE"),
    (InvalidDateFormatError, "INVALID_DATE_FORMAT"),
    (InvalidFieldError, "INVALID_FIELD"),
    (MissingRequiredArgError, "MISSING_REQUIRED_ARG"),
    (FileNotFoundCLIError, "FILE_NOT_FOUND"),
    (InvalidProfileError, "INVALID_PROFILE"),
    (UnsupportedLibraryTypeError, "UNSUPPORTED_LIBRARY_TYPE"),
]
NETWORK_ERROR_CASES = [
    (ApiTimeoutError, "API_TIMEOUT"),
    (ApiRateLimitError, "API_RATE_LIMIT"),
    (ApiServerError, "API_SERVER_ERROR"),
    (WebdavTimeoutError, "WEBDAV_TIMEOUT"),
    (WebdavConnectionError, "WEBDAV_CONNECTION_ERROR"),
    (NetworkError, "NETWORK_ERROR"),
    (StorageQuotaExceededError, "STORAGE_QUOTA_EXCEEDED"),
]
AUTH_ERROR_CASES = [
    (InvalidApiKeyError, "INVALID_API_KEY"),
    (InsufficientPermissionsError, "INSUFFICIENT_PERMISSIONS"),
    (WebdavAuthFailedError, "WEBDAV_AUTH_FAILED"),
]
LOCAL_ERROR_CASES = [
    (SqliteNotFoundError, "SQLITE_NOT_FOUND"),
    (SqliteLockedError, "SQLITE_LOCKED"),
    (SqliteSchemaIncompatibleError, "SQLITE_SCHEMA_INCOMPATIBLE"),
    (ConfigNotFoundError, "CONFIG_NOT_FOUND"),
    (ConfigInvalidError, "CONFIG_INVALID"),
    (AuditLogWriteFailedError, "AUDIT_LOG_WRITE_FAILED"),
    (WebdavFileExistsError, "WEBDAV_FILE_EXISTS"),
    (WebdavPropInvalidError, "WEBDAV_PROP_INVALID"),
    (Md5MismatchError, "MD5_MISMATCH"),
]
USAGE_ERROR_CASES = [
    (UsageError, "USAGE_ERROR"),
    (MutuallyExclusiveArgsError, "MUTUALLY_EXCLUSIVE_ARGS"),
]


@pytest.mark.parametrize("cls,code", USER_ERROR_CASES)
def test_user_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "user_error"
    assert err.exit_code == 1


@pytest.mark.parametrize("cls,code", NETWORK_ERROR_CASES)
def test_network_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "network_error"
    assert err.exit_code == 2


@pytest.mark.parametrize("cls,code", AUTH_ERROR_CASES)
def test_auth_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "auth_error"
    assert err.exit_code == 3


@pytest.mark.parametrize("cls,code", LOCAL_ERROR_CASES)
def test_local_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "local_error"
    assert err.exit_code == 4


@pytest.mark.parametrize("cls,code", USAGE_ERROR_CASES)
def test_usage_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "usage_error"
    assert err.exit_code == 64


class TestFromCode:
    def test_returns_correct_class(self) -> None:
        err = from_code("ITEM_NOT_FOUND", "item missing")
        assert isinstance(err, ItemNotFoundError)
        assert err.message == "item missing"

    def test_passes_kwargs(self) -> None:
        err = from_code("ITEM_NOT_FOUND", "msg", hint="try X", context={"k": "v"})
        assert err.hint == "try X"
        assert err.context == {"k": "v"}

    def test_unknown_code_falls_back_to_cli_error(self) -> None:
        err = from_code("DEFINITELY_NOT_REAL", "msg")
        assert type(err) is CLIError
        assert err.code == "DEFINITELY_NOT_REAL"
