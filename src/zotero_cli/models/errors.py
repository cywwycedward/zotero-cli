"""CLI error hierarchy. All raised exceptions in zotero-cli must subclass CLIError.

Per DEVELOPMENT.md §4.3 (error flow): adapters translate external library exceptions
into CLIError subclasses; services don't wrap; commands render Envelope and exit().

Per design §9.2: every error code maps to exactly one subclass.
"""

from __future__ import annotations

from typing import Any, Final, Literal

EXIT_USER_ERROR: Final[int] = 1
EXIT_NETWORK_ERROR: Final[int] = 2
EXIT_AUTH_ERROR: Final[int] = 3
EXIT_LOCAL_ERROR: Final[int] = 4
EXIT_USAGE_ERROR: Final[int] = 64

ErrorCategory = Literal[
    "user_error",
    "network_error",
    "auth_error",
    "local_error",
    "usage_error",
]


class CLIError(Exception):
    """Base class for all CLI-raised errors. Subclasses override class attrs."""

    code: str = "GENERIC"
    category: ErrorCategory = "user_error"
    exit_code: int = EXIT_USER_ERROR

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.context = context if context is not None else {}
        self.cause = cause


# user_error (1)
class ItemNotFoundError(CLIError):
    code = "ITEM_NOT_FOUND"


class CollectionNotFoundError(CLIError):
    code = "COLLECTION_NOT_FOUND"


class TagNotFoundError(CLIError):
    code = "TAG_NOT_FOUND"


class FeedNotFoundError(CLIError):
    code = "FEED_NOT_FOUND"


class InvalidItemTypeError(CLIError):
    code = "INVALID_ITEM_TYPE"


class UnsupportedExportFormatError(CLIError):
    code = "UNSUPPORTED_EXPORT_FORMAT"


class InvalidDateFormatError(CLIError):
    code = "INVALID_DATE_FORMAT"


class InvalidFieldError(CLIError):
    code = "INVALID_FIELD"


class MissingRequiredArgError(CLIError):
    code = "MISSING_REQUIRED_ARG"


class FileNotFoundCLIError(CLIError):
    code = "FILE_NOT_FOUND"


class InvalidProfileError(CLIError):
    code = "INVALID_PROFILE"


class UnsupportedLibraryTypeError(CLIError):
    code = "UNSUPPORTED_LIBRARY_TYPE"


class DoiNotFoundError(CLIError):
    code = "DOI_NOT_FOUND"


# network_error (2)
class _NetworkError(CLIError):
    category = "network_error"
    exit_code = EXIT_NETWORK_ERROR


class ApiTimeoutError(_NetworkError):
    code = "API_TIMEOUT"


class ApiRateLimitError(_NetworkError):
    code = "API_RATE_LIMIT"


class ApiServerError(_NetworkError):
    code = "API_SERVER_ERROR"


class WebdavTimeoutError(_NetworkError):
    code = "WEBDAV_TIMEOUT"


class WebdavConnectionError(_NetworkError):
    code = "WEBDAV_CONNECTION_ERROR"


class NetworkError(_NetworkError):
    code = "NETWORK_ERROR"


class StorageQuotaExceededError(_NetworkError):
    code = "STORAGE_QUOTA_EXCEEDED"


# auth_error (3)
class _AuthError(CLIError):
    category = "auth_error"
    exit_code = EXIT_AUTH_ERROR


class InvalidApiKeyError(_AuthError):
    code = "INVALID_API_KEY"


class InsufficientPermissionsError(_AuthError):
    code = "INSUFFICIENT_PERMISSIONS"


class WebdavAuthFailedError(_AuthError):
    code = "WEBDAV_AUTH_FAILED"


# local_error (4)
class _LocalError(CLIError):
    category = "local_error"
    exit_code = EXIT_LOCAL_ERROR


class SqliteNotFoundError(_LocalError):
    code = "SQLITE_NOT_FOUND"


class SqliteLockedError(_LocalError):
    code = "SQLITE_LOCKED"


class SqliteSchemaIncompatibleError(_LocalError):
    code = "SQLITE_SCHEMA_INCOMPATIBLE"


class ConfigNotFoundError(_LocalError):
    code = "CONFIG_NOT_FOUND"


class ConfigInvalidError(_LocalError):
    code = "CONFIG_INVALID"


class AuditLogWriteFailedError(_LocalError):
    code = "AUDIT_LOG_WRITE_FAILED"


class WebdavFileExistsError(_LocalError):
    code = "WEBDAV_FILE_EXISTS"


class WebdavPropInvalidError(_LocalError):
    code = "WEBDAV_PROP_INVALID"


class Md5MismatchError(_LocalError):
    code = "MD5_MISMATCH"


# usage_error (64)
class _UsageError(CLIError):
    category = "usage_error"
    exit_code = EXIT_USAGE_ERROR


class UsageError(_UsageError):
    code = "USAGE_ERROR"


class MutuallyExclusiveArgsError(_UsageError):
    code = "MUTUALLY_EXCLUSIVE_ARGS"


# Registry
_REGISTRY: dict[str, type[CLIError]] = {
    cls.code: cls
    for cls in [
        ItemNotFoundError,
        CollectionNotFoundError,
        TagNotFoundError,
        FeedNotFoundError,
        InvalidItemTypeError,
        UnsupportedExportFormatError,
        InvalidDateFormatError,
        InvalidFieldError,
        MissingRequiredArgError,
        FileNotFoundCLIError,
        InvalidProfileError,
        UnsupportedLibraryTypeError,
        DoiNotFoundError,
        ApiTimeoutError,
        ApiRateLimitError,
        ApiServerError,
        WebdavTimeoutError,
        WebdavConnectionError,
        NetworkError,
        StorageQuotaExceededError,
        InvalidApiKeyError,
        InsufficientPermissionsError,
        WebdavAuthFailedError,
        SqliteNotFoundError,
        SqliteLockedError,
        SqliteSchemaIncompatibleError,
        ConfigNotFoundError,
        ConfigInvalidError,
        AuditLogWriteFailedError,
        WebdavFileExistsError,
        WebdavPropInvalidError,
        Md5MismatchError,
        UsageError,
        MutuallyExclusiveArgsError,
    ]
}


def from_code(code: str, message: str, **kwargs: Any) -> CLIError:
    """Look up CLI error class by code string. Falls back to bare CLIError with
    custom code if unknown — used by adapters when external libs return new error
    codes we haven't classified yet."""
    cls = _REGISTRY.get(code)
    if cls is None:
        err = CLIError(message, **kwargs)
        err.code = code
        return err
    return cls(message, **kwargs)
