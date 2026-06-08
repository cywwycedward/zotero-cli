"""zotero_api.py — Thin pyzotero wrapper + exception translation + backend dispatch.

Per design §10.0.2: all Zotero Web API calls go through this adapter.
Per DEVELOPMENT.md §4.3: pyzotero exceptions are translated to CLIError subclasses.
"""
from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pyzotero import zotero_errors as zerr
from pyzotero.zotero import Zotero

from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.errors import (
    ApiRateLimitError,
    ApiServerError,
    ApiTimeoutError,
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

# Explicit alias per DEVELOPMENT.md §4.2 adapter boundary.
PyzoteroResponse: TypeAlias = dict[str, Any]
PyzoteroTemplate: TypeAlias = dict[str, Any]


# ── Task 4: _select_backend ────────────────────────────────────────────────


def _select_backend(profile: ProfileConfig) -> Literal["zfs", "webdav"]:
    """Choose attachment backend based on profile (design §10.0.2)."""
    return "webdav" if profile.webdav is not None else "zfs"


# ── Task 3: _map_pyzotero_exception ────────────────────────────────────────


def _map_pyzotero_exception(exc: Exception) -> CLIError:
    """Translate pyzotero exceptions to CLI error codes per design §10.0.2.6.

    Order: most specific first (isinstance chain), fallback to generic.
    """
    # user_error (1)
    if isinstance(exc, zerr.ParamNotPassedError):
        return MissingRequiredArgError(str(exc), cause=exc)
    if isinstance(exc, zerr.UnsupportedParamsError):
        return MutuallyExclusiveArgsError(str(exc), cause=exc)
    if isinstance(exc, zerr.FileDoesNotExistError):
        return FileNotFoundCLIError(str(exc), cause=exc)
    if isinstance(exc, zerr.ResourceNotFoundError):
        return ItemNotFoundError(str(exc), cause=exc)

    # auth_error (3)
    if isinstance(exc, zerr.UserNotAuthorisedError):
        # Try to distinguish 401 vs 403 from message or status
        msg = str(exc)
        if "403" in msg or "forbidden" in msg.lower():
            return InsufficientPermissionsError(str(exc), cause=exc)
        return InvalidApiKeyError(str(exc), cause=exc)

    # network_error (2)
    if isinstance(exc, zerr.TooManyRequestsError):
        return ApiRateLimitError(str(exc), cause=exc)
    if isinstance(exc, zerr.RequestEntityTooLargeError):
        return StorageQuotaExceededError(str(exc), cause=exc)
    if isinstance(exc, zerr.PreConditionFailedError):
        return ApiServerError(str(exc), cause=exc)
    if isinstance(exc, zerr.UploadError):
        # Distinguish timeout from generic network error
        if "timeout" in str(exc).lower():
            return ApiTimeoutError(str(exc), cause=exc)
        return NetworkError(str(exc), cause=exc)

    # Fallback — unmapped pyzotero error
    return CLIError(
        f"unmapped pyzotero error: {exc!r}",
        cause=exc,
    )


# ── Task 2: ZoteroAPI ──────────────────────────────────────────────────────


class ZoteroAPI:
    """Thin wrapper around pyzotero. Holds one Zotero instance per profile."""

    def __init__(self, profile: ProfileConfig) -> None:
        self._profile = profile
        self._zot = Zotero(
            library_id=profile.library_id,
            library_type=profile.library_type,
            api_key=profile.api_key,
        )

    @property
    def library_id(self) -> str:
        return self._profile.library_id
