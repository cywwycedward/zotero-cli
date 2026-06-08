"""Service-layer result types. All Item/Collection/Tag/Export services return
these TypedDicts (no bare dict[str, Any]).

Per design §8.1 / §8.2 / §7.2.1: services return (data, meta_extra) split, where
data goes into envelope.data and meta_extra is merged into envelope.meta.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

# --- Read operations (list / search / show) ---


class ListMetaExtra(TypedDict, total=False):
    count: int
    total: int
    limit: int
    start: int
    next_start: int | None
    library_id: str
    library_version: int


class ListServiceResult(TypedDict):
    data: list[dict[str, Any]]
    meta_extra: ListMetaExtra


class ShowServiceResult(TypedDict):
    data: dict[str, Any]
    meta_extra: NotRequired[dict[str, Any]]


# --- Write operations (create / update / delete / attach) ---


class MutationSuccessfulItem(TypedDict):
    index: int
    key: str
    version: int
    data: NotRequired[dict[str, Any]]


class MutationUnchangedItem(TypedDict):
    index: int
    key: str


class MutationFailedItem(TypedDict):
    index: int
    code: str
    message: str
    context: NotRequired[dict[str, Any]]


class MutationData(TypedDict):
    successful: list[MutationSuccessfulItem]
    unchanged: list[MutationUnchangedItem]
    failed: list[MutationFailedItem]


class MutationMetaExtra(TypedDict, total=False):
    affected_keys: list[str]
    library_id: str


class MutationServiceResult(TypedDict):
    data: MutationData
    meta_extra: MutationMetaExtra


# --- Dry-run ---


class DryRunData(TypedDict, total=False):
    dry_run: bool
    would_create: list[dict[str, Any]]
    would_update: list[dict[str, Any]]
    would_delete: list[str]
    would_upload: list[dict[str, Any]]


class DryRunServiceResult(TypedDict):
    data: DryRunData
    meta_extra: NotRequired[dict[str, Any]]


# --- Export (raw bytes / text) ---


class ExportServiceResult(TypedDict):
    """Raw export content; command layer writes to stdout or --output file."""

    data: bytes
    meta_extra: NotRequired[dict[str, Any]]


# --- Collections tree (mode=TREE) ---


class CollectionNode(TypedDict):
    """Recursive collection tree node, used by collections list (mode=TREE)."""

    key: str
    name: str
    items_count: int
    parent_key: str | None
    children: list[CollectionNode]


class CollectionTreeServiceResult(TypedDict):
    data: list[CollectionNode]
    meta_extra: NotRequired[dict[str, Any]]
