"""Attachment result types per design §8.3 envelope schema."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class AttachmentItem(TypedDict, total=False):
    """Single attachment result (uploaded or unchanged). Fields are the same in both states."""

    file: str
    attachment_key: str
    parent_item_key: str
    size_bytes: int
    md5: str
    version: int | None  # ZFS only; WebDAV → null
    webdav_path: str | None  # WebDAV only; ZFS → null
    mtime_ms: int | None  # WebDAV only; ZFS → null


class AttachmentFailedItem(TypedDict):
    file: str
    attachment_key: str | None
    parent_item_key: str
    code: str
    message: str
    context: NotRequired[dict[str, Any]]


class AttachmentData(TypedDict):
    backend: str  # "zfs" | "webdav"
    uploaded: list[AttachmentItem]
    unchanged: list[AttachmentItem]
    failed: list[AttachmentFailedItem]


class AttachmentServiceResult(TypedDict):
    data: AttachmentData
    meta_extra: AttachmentMetaExtra


class AttachmentMetaExtra(TypedDict, total=False):
    affected_keys: list[str]
    backend: str
