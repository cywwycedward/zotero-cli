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

    # -- Item read methods --

    def items_top(
        self, *, limit: int = 100, start: int = 0,
        collection: str | None = None, tag: str | None = None,
    ) -> list[PyzoteroResponse]:
        """List top-level items (excludes attachment/note children)."""
        try:
            kwargs: dict[str, Any] = {
                "limit": limit, "start": start, "itemType": "-attachment || note",
            }
            if collection:
                kwargs["collectionID"] = collection
            if tag:
                kwargs["tag"] = tag
            return self._zot.top(**kwargs)  # type: ignore[no-any-return]
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def items(
        self, *, limit: int = 100, start: int = 0,
        collection: str | None = None, tag: str | None = None,
    ) -> list[PyzoteroResponse]:
        """List all items."""
        try:
            kwargs: dict[str, Any] = {"limit": limit, "start": start}
            if collection:
                kwargs["collectionID"] = collection
            if tag:
                kwargs["tag"] = tag
            return self._zot.items(**kwargs)  # type: ignore[no-any-return]
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def item(self, key: str) -> PyzoteroResponse:
        """Get a single item by key. 404 → ItemNotFoundError."""
        try:
            return self._zot.item(key)  # type: ignore[no-any-return]
        except zerr.ResourceNotFoundError as e:
            raise ItemNotFoundError(f"Item {key!r} not found", cause=e) from e
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def search_items(
        self, query: str, *, limit: int = 100, start: int = 0,
    ) -> list[PyzoteroResponse]:
        """Search items by query string."""
        try:
            return self._zot.items(q=query, limit=limit, start=start)  # type: ignore[no-any-return]
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def top_count(self) -> int:
        """Return count of top-level items."""
        try:
            return self._zot.num_items()
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def count_items(
        self, collection: str | None = None, tag: str | None = None,
    ) -> int:
        """Return item count, optionally filtered."""
        try:
            if collection:
                return self._zot.num_collectionitems(collection)
            if tag:
                return self._zot.num_items()
            return self.top_count()
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def last_modified_version(self) -> int:
        """Return the library's last modified version."""
        try:
            return self._zot.last_modified_version()
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    # -- Write methods --

    def create_items(self, payloads: list[PyzoteroTemplate]) -> dict[str, Any]:
        """Create items. Returns normalized {successful, unchanged, failed}."""
        try:
            result = self._zot.create_items(payloads)
            return _normalize_batch_result(result, payloads)
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def update_item(self, item: PyzoteroResponse) -> bool:
        """Update an existing item. Returns True on success."""
        try:
            self._zot.update_item(item)
            return True
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    def delete_item(self, item: PyzoteroResponse) -> bool:
        """Delete an item. Returns True on success."""
        try:
            self._zot.delete_item(item)
            return True
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    # -- Collections (to be extended by collection service) --

    def collections(self) -> list[PyzoteroResponse]:
        """List all collections."""
        try:
            import json
            return json.loads(self._zot.collections())  # type: ignore[no-any-return]
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e

    # -- Tags (to be extended by tag service) --

    def tags(self) -> list[PyzoteroResponse]:
        """List all tags."""
        try:
            import json
            return json.loads(self._zot.tags())  # type: ignore[no-any-return]
        except zerr.PyZoteroError as e:
            raise _map_pyzotero_exception(e) from e


# ── Helper: normalize pyzotero batch result ────────────────────────────────


def _normalize_batch_result(
    result: dict[str, Any], payloads: list[PyzoteroTemplate],
) -> dict[str, Any]:
    """Normalize pyzotero's create_items result into {successful, unchanged, failed}."""
    normalized: dict[str, list[dict[str, Any]]] = {
        "successful": [], "unchanged": [], "failed": [],
    }

    successful = result.get("successful", {})
    unchanged = result.get("unchanged", {})
    failed = result.get("failed", {})

    for idx, payload in enumerate(payloads):
        key = payload.get("key", "")

        if idx in successful or key in successful:
            entry_key = successful.get(idx) or successful.get(key, "")
            normalized["successful"].append({
                "index": idx, "key": str(entry_key), "version": 0,
            })
        elif unchanged and key in unchanged:
            normalized["unchanged"].append({"index": idx, "key": key})
        elif failed and key in failed:
            fail_info = failed[key] if isinstance(failed, dict) else str(failed)
            normalized["failed"].append({
                "index": idx,
                "code": "INVALID_ITEM_TYPE",
                "message": str(fail_info),
            })

    return normalized
