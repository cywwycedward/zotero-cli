"""Full-text retrieval service."""

from __future__ import annotations

from typing import cast

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.results import FulltextData, FulltextServiceResult


class FulltextService:
    """Retrieve full-text content for Zotero attachment items."""

    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    @classmethod
    def from_profile(cls, profile: ProfileConfig) -> FulltextService:
        return cls(ZoteroAPI(profile))

    def get(self, key: str) -> FulltextServiceResult:
        raw = self._api.fulltext_item(key)
        data = cast(FulltextData, {**raw, "key": key})
        content = data.get("content", "")
        return {
            "data": data,
            "meta_extra": {
                "item_key": key,
                "content_length": len(content),
            },
        }
