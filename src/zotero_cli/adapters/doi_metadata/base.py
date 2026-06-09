"""src/zotero_cli/adapters/doi_metadata/base.py — Provider protocol for DOI metadata sources."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class DoiMetadataProvider(Protocol):
    source: str

    def fetch(self, doi: str) -> dict[str, Any]: ...

    def to_zotero_item(
        self,
        raw: dict[str, Any],
        *,
        doi: str,
        item_template: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]: ...
