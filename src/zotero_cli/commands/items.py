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

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.models.errors import CLIError, MutuallyExclusiveArgsError
from zotero_cli.services.config_service import load_config
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
        command=command, mode=mode, options=options,
        work=runner_work, meta_extra=captured_meta,
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
            write_entry(log_path=log_path, entry=AuditEntry(
                timestamp=_now_iso(), profile=options.profile, command=command,
                args=args_for_audit or {}, result="success",
                affected_keys=(meta_extra or {}).get("affected_keys", []),
                elapsed_ms=int(elapsed),
            ))
            return data
        except CLIError as err:
            elapsed = (time.perf_counter_ns() - start_ns) // 1_000_000
            write_entry(log_path=log_path, entry=AuditEntry(
                timestamp=_now_iso(), profile=options.profile, command=command,
                args=args_for_audit or {}, result="failure",
                affected_keys=[], elapsed_ms=int(elapsed),
                error_code=err.code, error_message=err.message,
            ))
            raise

    run_command(
        command=command, mode=OutputMode.SUMMARY, options=options,
        work=runner_work, meta_extra=captured_meta,
    )


def _field_filter(ctx: typer.Context, all_fields: bool) -> list[str] | None:
    options: GlobalOptions = ctx.obj
    if all_fields:
        return None
    return load_config(
        profile=options.profile, config_path=options.config_path,
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
    all_fields: Annotated[
        bool, typer.Option("--all-fields", help="Show all fields")
    ] = False,
) -> None:
    """List items in the library."""
    profile = _get_profile(ctx)
    field_filter = _field_filter(ctx, all_fields)

    def work() -> tuple[Any, dict[str, Any] | None]:
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.list(limit=limit, collection=collection, tag=tag)
        return result["data"], dict(result["meta_extra"])

    _invoke(ctx, "items.list", OutputMode.KV_LIST, work, field_filter=field_filter)


# ── search ─────────────────────────────────────────────────────────────────


@app.command("search")
def search_items(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query")],
    limit: Annotated[int, typer.Option("--limit", help="Max items")] = 100,
    all_fields: Annotated[
        bool, typer.Option("--all-fields", help="Show all fields")
    ] = False,
) -> None:
    """Search items by query string."""
    profile = _get_profile(ctx)
    field_filter = _field_filter(ctx, all_fields)

    def work() -> tuple[Any, dict[str, Any] | None]:
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.search(query, limit=limit)
        return result["data"], dict(result["meta_extra"])

    _invoke(ctx, "items.search", OutputMode.KV_LIST, work, field_filter=field_filter)


# ── show ───────────────────────────────────────────────────────────────────


@app.command("show")
def show_item(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Item key")],
    all_fields: Annotated[
        bool, typer.Option("--all-fields", help="Show all fields")
    ] = False,
) -> None:
    """Show a single item by key."""
    profile = _get_profile(ctx)
    field_filter = _field_filter(ctx, all_fields)

    def work() -> tuple[Any, dict[str, Any] | None]:
        api = ZoteroAPI(profile)
        svc = ItemService(api)
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
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without creating")
    ] = False,
) -> None:
    """Create a new item."""
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

    def action() -> tuple[Any, Any]:
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.create([payload])
        return result["data"], result["meta_extra"]

    _invoke_write(
        ctx, "items.create", action,
        args_for_audit={"item_type": item_type, "title": title, "dry_run": dry_run},
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
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without updating")
    ] = False,
) -> None:
    """Update an existing item."""
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
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.update(key, patch=patch)
        return result["data"], result["meta_extra"]

    _invoke_write(
        ctx, "items.update", action,
        args_for_audit={"key": key, "dry_run": dry_run},
    )


# ── delete ─────────────────────────────────────────────────────────────────


@app.command("delete")
def delete_item(
    ctx: typer.Context,
    keys: Annotated[list[str], typer.Argument(help="Item keys to delete")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without deleting")
    ] = False,
) -> None:
    """Delete one or more items."""
    profile = _get_profile(ctx)

    def action() -> tuple[Any, Any]:
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.delete(list(keys))
        return result["data"], result["meta_extra"]

    _invoke_write(
        ctx, "items.delete", action,
        args_for_audit={"keys": keys, "dry_run": dry_run},
    )


# ── export ─────────────────────────────────────────────────────────────────


@app.command("export")
def export_items(
    ctx: typer.Context,
    export_format: Annotated[
        str, typer.Option("--format", help="bibtex / ris / csljson / ...")
    ] = "bibtex",
    collection: Annotated[
        str | None, typer.Option("--collection", help="Filter by collection key")
    ] = None,
    tag: Annotated[
        str | None, typer.Option("--tag", help="Filter by tag")
    ] = None,
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
            "items.export", 0, options,
        )
        sys.exit(64)
    if options.quiet:
        emit_failure(
            MutuallyExclusiveArgsError(
                "--quiet is not supported for export",
                hint="export writes raw content; --quiet has no key concept.",
            ),
            "items.export", 0, options,
        )
        sys.exit(64)

    start = time.perf_counter()
    try:
        profile = _get_profile(ctx)
        api = ZoteroAPI(profile)
        svc = ExportService(api)
        result = svc.export(export_format, collection=collection, tag=tag)
    except CLIError as err:
        elapsed = int((time.perf_counter() - start) * 1000)
        emit_failure(err, "items.export", elapsed, options)
        sys.exit(err.exit_code)
    elapsed = int((time.perf_counter() - start) * 1000)

    raw_bytes: bytes = result["data"]
    byte_size = len(raw_bytes)

    if options.json_mode:
        env = Envelope.success(
            data={
                "format": export_format,
                "content": raw_bytes.decode("utf-8", errors="replace"),
                "byte_size": byte_size,
            },
            command="items.export",
            elapsed_ms=elapsed,
            meta_extra=result.get("meta_extra"),
        )
        sys.stdout.write(env.model_dump_json(indent=2) + "\n")
        sys.exit(0)

    if output is not None:
        output.write_bytes(raw_bytes)
        sys.stderr.write(f"Exported {byte_size} bytes to {output}\n")
    else:
        sys.stdout.buffer.write(raw_bytes)
    sys.exit(0)
