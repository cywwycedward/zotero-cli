"""commands/items.py — item subcommands: list, search, show, create, update, delete, export.

Per DEVELOPMENT.md §5.2: all commands go through run_command for stdout/stderr split.
Write commands attach audit log entries per design §9.4.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from zotero_cli.adapters.doi_metadata.crossref import CrossrefProvider
from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.models.errors import CLIError, MutuallyExclusiveArgsError
from zotero_cli.services.config_service import load_config
from zotero_cli.services.doi_item_service import DoiItemService
from zotero_cli.services.item_service import ItemService
from zotero_cli.utils.audit_log import AuditEntry, write_entry
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Item operations")


def _audit_log_path() -> Path:
    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return base / "zotero-cli" / "audit.log"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _invoke(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    work: Callable[[], tuple[Any, dict[str, Any] | None]],
    *,
    field_filter: list[str] | None = None,
) -> None:
    options: GlobalOptions = ctx.obj
    captured_meta: dict[str, Any] = {}

    def runner_work() -> Any:
        data, meta_extra = work()
        if meta_extra:
            captured_meta.update(meta_extra)
        return data

    run_command(
        command=command,
        mode=mode,
        options=options,
        work=runner_work,
        meta_extra=captured_meta,
        field_filter=field_filter,
    )


def _invoke_write(
    ctx: typer.Context,
    command: str,
    action: Callable[..., tuple[Any, Any]],
    *,
    args_for_audit: dict[str, Any] | None = None,
) -> None:
    """Write command wrapper with audit logging."""
    options: GlobalOptions = ctx.obj
    log_path = _audit_log_path()
    captured_meta: dict[str, Any] = {}

    def runner_work() -> Any:
        start_ns = time.perf_counter_ns()
        try:
            data, meta_extra = action()
            elapsed = (time.perf_counter_ns() - start_ns) // 1_000_000
            captured_meta.update(meta_extra or {})
            write_entry(
                log_path=log_path,
                entry=AuditEntry(
                    timestamp=_now_iso(),
                    profile=options.profile,
                    command=command,
                    args=args_for_audit or {},
                    result="success",
                    affected_keys=(meta_extra or {}).get("affected_keys", []),
                    elapsed_ms=int(elapsed),
                ),
            )
            return data
        except CLIError as err:
            elapsed = (time.perf_counter_ns() - start_ns) // 1_000_000
            write_entry(
                log_path=log_path,
                entry=AuditEntry(
                    timestamp=_now_iso(),
                    profile=options.profile,
                    command=command,
                    args=args_for_audit or {},
                    result="failure",
                    affected_keys=[],
                    elapsed_ms=int(elapsed),
                    error_code=err.code,
                    error_message=err.message,
                ),
            )
            raise

    run_command(
        command=command,
        mode=OutputMode.SUMMARY,
        options=options,
        work=runner_work,
        meta_extra=captured_meta,
    )


def _field_filter(ctx: typer.Context, all_fields: bool) -> list[str] | None:
    options: GlobalOptions = ctx.obj
    if all_fields:
        return None
    return load_config(
        profile=options.profile,
        config_path=options.config_path,
    ).item_fields.list


def _get_profile(ctx: typer.Context) -> Any:
    options: GlobalOptions = ctx.obj
    return load_config(profile=options.profile, config_path=options.config_path)


# ── list ───────────────────────────────────────────────────────────────────


@app.command("list")
def list_items(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", help="Max items")] = 100,
    collection: Annotated[
        str | None, typer.Option("--collection", help="Filter by collection key")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter by tag")] = None,
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """List items in the library."""
    profile = _get_profile(ctx)
    field_filter = _field_filter(ctx, all_fields)

    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = ItemService.from_profile(profile)
        result = svc.list(limit=limit, collection=collection, tag=tag)
        return result["data"], dict(result["meta_extra"])

    _invoke(ctx, "items.list", OutputMode.KV_LIST, work, field_filter=field_filter)


# ── search ─────────────────────────────────────────────────────────────────


@app.command("search")
def search_items(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option("--limit", help="Max items")] = 100,
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """Search items by query string."""
    profile = _get_profile(ctx)
    field_filter = _field_filter(ctx, all_fields)

    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = ItemService.from_profile(profile)
        result = svc.search(query, limit=limit)
        return result["data"], dict(result["meta_extra"])

    _invoke(ctx, "items.search", OutputMode.KV_LIST, work, field_filter=field_filter)


# ── show ───────────────────────────────────────────────────────────────────


@app.command("show")
def show_item(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Item key")],
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """Show a single item by key."""
    profile = _get_profile(ctx)
    field_filter = _field_filter(ctx, all_fields)

    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = ItemService.from_profile(profile)
        result = svc.show(key)
        return result["data"], None

    _invoke(ctx, "items.show", OutputMode.KV, work, field_filter=field_filter)


# ── create ─────────────────────────────────────────────────────────────────


@app.command("create")
def create_item(
    ctx: typer.Context,
    item_type: Annotated[
        str, typer.Option("--type", help="Item type (e.g. journalArticle)")
    ] = "journalArticle",
    title: Annotated[str, typer.Option("--title", help="Item title")] = "",
    creators: Annotated[str | None, typer.Option("--creators", help="Creators JSON")] = None,
    date: Annotated[str | None, typer.Option("--date", help="Publication date")] = None,
    doi: Annotated[str | None, typer.Option("--doi", help="DOI")] = None,
    url: Annotated[str | None, typer.Option("--url", help="URL")] = None,
    tags: Annotated[str | None, typer.Option("--tags", help="Comma-separated tags")] = None,
    collection: Annotated[
        str | None, typer.Option("--collection", help="Add to collection")
    ] = None,
    attach: Annotated[Path | None, typer.Option("--attach", help="Attach a PDF file")] = None,
    attach_title: Annotated[
        str | None, typer.Option("--attach-title", help="Attachment title")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without creating")] = False,
) -> None:
    """Create a new item, optionally with an attachment."""
    from zotero_cli.services.attachment_service import AttachmentService

    profile = _get_profile(ctx)
    import json as _json

    payload: dict[str, Any] = {"itemType": item_type, "title": title}
    if creators:
        payload["creators"] = _json.loads(creators)
    if date:
        payload["date"] = date
    if doi:
        payload["DOI"] = doi
    if url:
        payload["url"] = url
    if tags:
        payload["tags"] = [{"tag": t.strip()} for t in tags.split(",")]
    if collection:
        payload["collections"] = [collection]

    def action() -> tuple[Any, Any]:
        if dry_run:
            preview: dict[str, Any] = {"dry_run": True, "would_create": [payload]}
            if attach is not None:
                preview["would_upload"] = [str(attach)]
            return preview, {"dry_run": True}
        svc = ItemService.from_profile(profile)
        result = svc.create([payload])
        # Upload attachment if --attach was provided
        if attach is not None:
            affected = result["meta_extra"].get("affected_keys", [])
            if not affected:
                raise CLIError(
                    "Item created but server returned no item key; cannot attach file",
                    hint="Re-run without --attach and attach manually",
                )
            parent_key = affected[0]
            att_svc = AttachmentService(profile)
            att_result = att_svc.attach(
                parent_key,
                attach,
                title=attach_title,
            )
            att_keys = att_result["meta_extra"].get("affected_keys", [])
            return att_result["data"], {"affected_keys": affected + att_keys}
        return result["data"], result["meta_extra"]

    _invoke_write(
        ctx,
        "items.create",
        action,
        args_for_audit={
            "item_type": item_type,
            "title": title,
            "collection": collection,
            "dry_run": dry_run,
        },
    )


# ── add-doi ───────────────────────────────────────────────────────────────


@app.command("add-doi")
def add_doi(
    ctx: typer.Context,
    doi: Annotated[str, typer.Argument(help="DOI, doi: prefix, or DOI URL")],
    collection: Annotated[
        str | None, typer.Option("--collection", help="Add to collection")
    ] = None,
    tags: Annotated[str | None, typer.Option("--tags", help="Comma-separated tags")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without creating")] = False,
) -> None:
    """Create an item by resolving metadata from a DOI via CrossRef."""
    profile = _get_profile(ctx)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    def action() -> tuple[Any, Any]:
        api = ZoteroAPI(profile)
        provider = CrossrefProvider(crossref_email=getattr(profile, "crossref_email", None))
        svc = DoiItemService(
            api=api,
            item_service=ItemService(api),
            provider=provider,
        )
        result = svc.add_by_doi(
            doi,
            dry_run=dry_run,
            tags=tag_list,
            collection=collection,
        )
        return result["data"], result.get("meta_extra")

    _invoke_write(
        ctx,
        "items.add_doi",
        action,
        args_for_audit={"doi": doi, "collection": collection, "dry_run": dry_run},
    )


# ── update ─────────────────────────────────────────────────────────────────


@app.command("update")
def update_item(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Item key")],
    title: Annotated[str | None, typer.Option("--title", help="New title")] = None,
    date: Annotated[str | None, typer.Option("--date", help="New date")] = None,
    tags: Annotated[
        str | None, typer.Option("--tags", help="Replace tags (comma-separated)")
    ] = None,
    add_tags: Annotated[
        str | None, typer.Option("--add-tags", help="Add tags (comma-separated)")
    ] = None,
    json_patch: Annotated[
        str | None, typer.Option("--json-patch", help="JSON patch to merge")
    ] = None,
    attach: Annotated[Path | None, typer.Option("--attach", help="Attach a PDF file")] = None,
    attach_title: Annotated[
        str | None, typer.Option("--attach-title", help="Attachment title")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without updating")] = False,
) -> None:
    """Update an existing item, optionally adding an attachment."""
    from zotero_cli.services.attachment_service import AttachmentService

    profile = _get_profile(ctx)
    import json as _json

    patch: dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
    if date is not None:
        patch["date"] = date
    if tags is not None:
        patch["tags"] = [{"tag": t.strip()} for t in tags.split(",")]
    if add_tags is not None:
        patch["add_tags"] = [t.strip() for t in add_tags.split(",")]
    if json_patch is not None:
        patch.update(_json.loads(json_patch))

    def action() -> tuple[Any, Any]:
        if dry_run:
            preview: dict[str, Any] = {"dry_run": True, "would_update": {"key": key, **patch}}
            if attach is not None:
                preview["would_upload"] = [str(attach)]
            return preview, {"dry_run": True}
        svc = ItemService.from_profile(profile)
        if patch:
            result = svc.update(key, patch=patch)
            item_data, item_meta = result["data"], result["meta_extra"]
        else:
            item_data = {
                "successful": [{"index": 0, "key": key, "version": 0}],
                "unchanged": [],
                "failed": [],
            }
            item_meta = {"affected_keys": [key]}
        if attach is not None:
            att_svc = AttachmentService(profile)
            att_result = att_svc.attach(key, attach, title=attach_title)
            att_keys = att_result["meta_extra"].get("affected_keys", [])
            item_keys = item_meta.get("affected_keys", [])
            return att_result["data"], {"affected_keys": item_keys + att_keys}
        return item_data, item_meta

    _invoke_write(
        ctx,
        "items.update",
        action,
        args_for_audit={"key": key, "dry_run": dry_run},
    )


# ── delete ─────────────────────────────────────────────────────────────────


@app.command("delete")
def delete_item(
    ctx: typer.Context,
    keys: Annotated[list[str], typer.Argument(help="Item keys to delete")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without deleting")] = False,
) -> None:
    """Delete one or more items."""
    profile = _get_profile(ctx)

    def action() -> tuple[Any, Any]:
        if dry_run:
            return {"dry_run": True, "would_delete": list(keys)}, {"dry_run": True}
        svc = ItemService.from_profile(profile)
        result = svc.delete(list(keys))
        return result["data"], result["meta_extra"]

    _invoke_write(
        ctx,
        "items.delete",
        action,
        args_for_audit={"keys": keys, "dry_run": dry_run},
    )


# ── attach ─────────────────────────────────────────────────────────────────


@app.command("attach")
def attach_file(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Parent item key")],
    file: Annotated[Path, typer.Argument(help="PDF file to attach")],
    title: Annotated[str | None, typer.Option("--title", help="Attachment title")] = None,
    reuse_key: Annotated[
        str | None, typer.Option("--reuse-key", help="Reuse existing attachment key")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Force reupload (WebDAV only)")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without uploading")] = False,
) -> None:
    """Attach a file to an existing item."""
    from zotero_cli.services.attachment_service import AttachmentService

    profile = _get_profile(ctx)

    def action() -> tuple[Any, Any]:
        if dry_run:
            preview: dict[str, Any] = {
                "dry_run": True,
                "would_upload": [{"parent_key": key, "file": str(file)}],
            }
            if reuse_key:
                preview["would_upload"][0]["reuse_key"] = reuse_key
            return preview, {"dry_run": True}
        att_svc = AttachmentService(profile)
        result = att_svc.attach(
            key,
            file,
            reuse_key=reuse_key,
            force=force,
            title=title,
        )
        return result["data"], result["meta_extra"]

    _invoke_write(
        ctx,
        "items.attach",
        action,
        args_for_audit={"key": key, "file": str(file), "reuse_key": reuse_key, "dry_run": dry_run},
    )


# ── export ─────────────────────────────────────────────────────────────────


@app.command("export")
def export_items(
    ctx: typer.Context,
    export_format: Annotated[
        str, typer.Option("--format", help="bibtex / ris / csljson / ...")
    ] = "bibtex",
    limit: Annotated[int, typer.Option("--limit", help="Max items to export")] = 100,
    collection: Annotated[
        str | None, typer.Option("--collection", help="Filter by collection key")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter by tag")] = None,
    output: Annotated[
        Path | None, typer.Option("--output", help="Write to file instead of stdout")
    ] = None,
) -> None:
    """Export items in the requested format (bibtex, ris, csljson, etc.)."""
    import sys

    from zotero_cli.commands._runner import emit_failure
    from zotero_cli.models.envelope import Envelope
    from zotero_cli.services.export_service import ExportService

    options: GlobalOptions = ctx.obj

    if options.json_mode and options.quiet:
        emit_failure(
            MutuallyExclusiveArgsError(
                "--json and --quiet cannot be combined",
                hint="Use --json for full envelope.",
            ),
            "items.export",
            0,
            options,
        )
        sys.exit(64)
    if options.quiet:
        emit_failure(
            MutuallyExclusiveArgsError(
                "--quiet is not supported for export",
                hint="export writes raw content; --quiet has no key concept.",
            ),
            "items.export",
            0,
            options,
        )
        sys.exit(64)

    start = time.perf_counter()
    try:
        profile = _get_profile(ctx)
        svc = ExportService.from_profile(profile)
        result = svc.export(export_format, collection=collection, tag=tag, limit=limit)
    except CLIError as err:
        elapsed = int((time.perf_counter() - start) * 1000)
        emit_failure(err, "items.export", elapsed, options)
        sys.exit(err.exit_code)
    elapsed = int((time.perf_counter() - start) * 1000)

    raw_bytes: bytes = result["data"]
    byte_size = len(raw_bytes)

    if output is not None:
        output.write_bytes(raw_bytes)

    if options.json_mode:
        data: dict[str, Any] = {
            "format": export_format,
            "byte_size": byte_size,
        }
        if output is not None:
            data["output_path"] = str(output)
        else:
            data["content"] = raw_bytes.decode("utf-8", errors="replace")
        env = Envelope.success(
            data=data,
            command="items.export",
            elapsed_ms=elapsed,
            meta_extra=result.get("meta_extra"),
        )
        sys.stdout.write(env.model_dump_json(indent=2) + "\n")
        sys.exit(0)

    if output is not None:
        sys.stderr.write(f"Exported {byte_size} bytes to {output}\n")
    else:
        sys.stdout.buffer.write(raw_bytes)
    sys.exit(0)
