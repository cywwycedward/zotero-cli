"""ExportService — exports items in requested format."""

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.results import ExportServiceResult


class ExportService:
    """Export items to BibTeX, RIS, CSL JSON, etc."""

    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    def export(
        self,
        export_format: str,
        *,
        collection: str | None = None,
        tag: str | None = None,
    ) -> ExportServiceResult:
        raw = self._api.export_items(export_format, collection=collection, tag=tag)
        return {
            "data": raw,
            "meta_extra": {
                "format": export_format,
                "byte_size": len(raw),
            },
        }
