"""AttachmentService — dual-backend attachment upload orchestrator (design §10.0).

Dispatches between ZFS (pyzotero) and WebDAV (self-implemented) backends
based on profile config. Handles validation, rollback, and envelope formatting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zotero_cli.adapters.webdav_client import WebDAVStorage, upload_attachment_webdav
from zotero_cli.adapters.zotero_api import ZoteroAPI, _select_backend
from zotero_cli.models.attachment import AttachmentServiceResult
from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.errors import MutuallyExclusiveArgsError, UnsupportedLibraryTypeError


class AttachmentService:
    """Orchestrates attachment uploads across ZFS and WebDAV backends."""

    def __init__(self, profile: ProfileConfig) -> None:
        self._profile = profile
        self._backend = _select_backend(profile)
        self._api = ZoteroAPI(profile)

    @property
    def backend(self) -> str:
        return self._backend

    def attach(
        self,
        parent_key: str,
        file_path: Path,
        *,
        reuse_key: str | None = None,
        force: bool = False,
        title: str | None = None,
    ) -> Any:
        """Upload a single attachment file. Dispatches to ZFS or WebDAV backend."""
        # Pre-validation: group library + WebDAV = unsupported
        if self._profile.library_type == "group" and self._backend == "webdav":
            raise UnsupportedLibraryTypeError(
                "WebDAV attachment upload is not supported for group libraries",
                hint="Remove [webdav] from your group profile config.",
            )

        # ZFS: --force is forbidden (§10.0.2.3)
        if self._backend == "zfs" and force:
            raise MutuallyExclusiveArgsError(
                "--force is only supported with WebDAV backend",
                hint="ZFS backend uses md5-based idempotency.",
            )

        # Validate reuse_key exists on server before upload
        if reuse_key:
            self._api.item(reuse_key)  # raises ItemNotFoundError if missing

        if self._backend == "webdav":
            return self._attach_webdav(
                parent_key, file_path, reuse_key=reuse_key, force=force, title=title
            )

        return self._attach_zfs(parent_key, file_path, reuse_key=reuse_key, title=title)

    def _attach_zfs(
        self,
        parent_key: str,
        file_path: Path,
        *,
        reuse_key: str | None = None,
        title: str | None = None,
    ) -> Any:
        """Upload via ZFS (pyzotero)."""
        if not file_path.exists():
            from zotero_cli.models.errors import FileNotFoundCLIError

            raise FileNotFoundCLIError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size

        try:
            if reuse_key:
                tpl = self._api.item_template("attachment", "imported_file")
                tpl["key"] = reuse_key
                tpl["filename"] = str(file_path)
                tpl["title"] = title or file_path.name
                result = self._api.upload_attachments([tpl], parentid=None)
            else:
                if title:
                    result = self._api.attachment_both(
                        [(title, str(file_path))],
                        parentid=parent_key,
                    )
                else:
                    result = self._api.attachment_simple(
                        [str(file_path)],
                        parentid=parent_key,
                    )
            return _format_zfs_result(result, file_path.name, parent_key, file_size)
        except Exception as e:
            from zotero_cli.adapters.zotero_api import _map_pyzotero_exception

            raise _map_pyzotero_exception(e) from e

    def _attach_webdav(
        self,
        parent_key: str,
        file_path: Path,
        *,
        reuse_key: str | None = None,
        force: bool = False,
        title: str | None = None,
    ) -> Any:
        """Upload via WebDAV self-implemented protocol."""
        if self._profile.webdav is None:
            raise UnsupportedLibraryTypeError("WebDAV config required for webdav backend")

        storage = WebDAVStorage(self._profile.webdav)
        result = upload_attachment_webdav(
            storage,
            parent_key,
            file_path,
            self._api,
            reuse_key=reuse_key,
            force=force,
            title=title,
        )
        return _format_webdav_result(result)

    def attach_multi(
        self,
        parent_key: str,
        file_paths: list[Path],
        *,
        reuse_keys: list[str] | None = None,
        force: bool = False,
    ) -> Any:
        """Upload multiple files, with concurrency for WebDAV (>=2 files)."""
        all_successful: list[Any] = []
        all_unchanged: list[Any] = []
        all_failed: list[Any] = []
        affected: list[str] = []

        keys_iter = reuse_keys if reuse_keys else [None] * len(file_paths)

        if self._backend == "webdav" and len(file_paths) >= 2:
            from concurrent.futures import ThreadPoolExecutor

            from zotero_cli.constants import DEFAULT_PARALLEL_UPLOADS

            with ThreadPoolExecutor(max_workers=DEFAULT_PARALLEL_UPLOADS) as pool:
                futures = []
                for fp, rk in zip(file_paths, keys_iter, strict=False):
                    f = pool.submit(
                        self.attach,
                        parent_key,
                        fp,
                        reuse_key=rk,
                        force=force,
                    )
                    futures.append(f)
                for f in futures:
                    r = f.result()
                    _merge_attach_result(r, all_successful, all_unchanged, all_failed, affected)
        else:
            for fp, rk in zip(file_paths, keys_iter, strict=False):
                r = self.attach(parent_key, fp, reuse_key=rk, force=force)
                _merge_attach_result(r, all_successful, all_unchanged, all_failed, affected)

        return {
            "data": {
                "backend": self._backend,
                "successful": all_successful,
                "unchanged": all_unchanged,
                "failed": all_failed,
            },
            "meta_extra": {
                "affected_keys": affected,
                "backend": self._backend,
            },
        }


def _format_zfs_result(
    result: dict[str, Any],
    file_name: str,
    parent_key: str,
    file_size: int,
) -> Any:
    """Format pyzotero attachment result into unified envelope schema."""
    successful: list[Any] = []
    unchanged: list[Any] = []
    failed: list[Any] = []
    affected: list[str] = []

    for s in result.get("success", result.get("successful", [])):
        key = s if isinstance(s, str) else s.get("key", "")
        successful.append(
            {
                "key": str(key),
                "file": file_name,
                "attachment_key": str(key),
                "parent_item_key": parent_key,
                "size_bytes": file_size,
                "md5": "",
                "version": 0,
                "webdav_path": None,
                "mtime_ms": None,
            }
        )
        if key:
            affected.append(str(key))

    for u in result.get("unchanged", []):
        key = u if isinstance(u, str) else u.get("key", "")
        unchanged.append(
            {
                "key": str(key),
                "file": file_name,
                "attachment_key": str(key),
                "parent_item_key": parent_key,
                "size_bytes": file_size,
                "md5": "",
                "version": None,
                "webdav_path": None,
                "mtime_ms": None,
            }
        )

    for f_item in result.get("failure", result.get("failed", [])):
        failed.append(
            {
                "file": file_name,
                "attachment_key": f_item if isinstance(f_item, str) else f_item.get("key"),
                "parent_item_key": parent_key,
                "code": "API_SERVER_ERROR",
                "message": str(f_item),
            }
        )

    return {
        "data": {
            "backend": "zfs",
            "successful": successful,
            "unchanged": unchanged,
            "failed": failed,
        },
        "meta_extra": {"affected_keys": affected, "backend": "zfs"},
    }


def _format_webdav_result(result: dict[str, Any]) -> Any:
    uploaded = result.get("uploaded", [])
    successful = [{"key": u.get("attachment_key", ""), **u} for u in uploaded]
    affected = [u.get("attachment_key", "") for u in uploaded]
    return {
        "data": {
            "backend": result.get("backend", "webdav"),
            "successful": successful,
            "unchanged": result.get("unchanged", []),
            "failed": result.get("failed", []),
        },
        "meta_extra": {"affected_keys": [a for a in affected if a], "backend": "webdav"},
    }


def _merge_attach_result(
    r: AttachmentServiceResult,
    all_uploaded: list[Any],
    all_unchanged: list[Any],
    all_failed: list[Any],
    affected: list[str],
) -> None:
    d: dict[str, Any] = r["data"]  # type: ignore[assignment]
    all_uploaded.extend(d.get("successful", []))
    all_unchanged.extend(d.get("unchanged", []))
    all_failed.extend(d.get("failed", []))
    affected.extend(r.get("meta_extra", {}).get("affected_keys", []))
