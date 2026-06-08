"""commands/items.py — item subcommands: list, search, show, create, update, delete.

Per DEVELOPMENT.md §5.2: all commands go through run_command for stdout/stderr split.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Callable

import typer

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.services.config_service import load_config
from zotero_cli.services.item_service import ItemService
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Item operations")


def _invoke(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    work: Callable[[], tuple[Any, dict[str, Any] | None]],
    *,
    field_filter: list[str] | None = None,
) -> None:
    """Wrap work in run_command. work returns (data, meta_extra) tuple."""
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


# ── list ───────────────────────────────────────────────────────────────────


@app.command("list")
def list_items(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", help="Max items")] = 100,
    collection: Annotated[str | None, typer.Option("--collection", help="Filter by collection key")] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter by tag")] = None,
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """List items in the library."""
    options: GlobalOptions = ctx.obj

    def work() -> tuple[Any, dict[str, Any] | None]:
        profile = load_config(
            profile=options.profile, config_path=options.config_path,
        )
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.list(limit=limit, collection=collection, tag=tag)
        return result["data"], dict(result["meta_extra"])

    field_filter = None if all_fields else load_config(profile=options.profile).item_fields.list
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
    options: GlobalOptions = ctx.obj

    def work() -> tuple[Any, dict[str, Any] | None]:
        profile = load_config(profile=options.profile, config_path=options.config_path)
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.search(query, limit=limit)
        return result["data"], dict(result["meta_extra"])

    field_filter = None if all_fields else load_config(profile=options.profile).item_fields.list
    _invoke(ctx, "items.search", OutputMode.KV_LIST, work, field_filter=field_filter)


# ── show ───────────────────────────────────────────────────────────────────


@app.command("show")
def show_item(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Item key")],
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """Show a single item by key."""
    options: GlobalOptions = ctx.obj

    def work() -> tuple[Any, dict[str, Any] | None]:
        profile = load_config(profile=options.profile, config_path=options.config_path)
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.show(key)
        return result["data"], None

    field_filter = None if all_fields else load_config(profile=options.profile).item_fields.list
    _invoke(ctx, "items.show", OutputMode.KV, work, field_filter=field_filter)


# ── export ─────────────────────────────────────────────────────────────────


@app.command("export")
def export_items(
    ctx: typer.Context,
    export_format: Annotated[str, typer.Option("--format", help="bibtex / ris / csljson / ...")] = "bibtex",
    collection: Annotated[str | None, typer.Option("--collection", help="Filter by collection key")] = None,
    output: Annotated[Path | None, typer.Option("--output", help="Write to file instead of stdout")] = None,
) -> None:
    """Export items in the requested format (bibtex, ris, csljson, etc.)."""
    import sys
    import time
    from pathlib import Path

    from zotero_cli.commands._runner import emit_failure
    from zotero_cli.models.envelope import Envelope
    from zotero_cli.models.errors import CLIError, MutuallyExclusiveArgsError
    from zotero_cli.services.export_service import ExportService

    options: GlobalOptions = ctx.obj

    if options.json_mode and options.quiet:
        err = MutuallyExclusiveArgsError(
            "--json and --quiet cannot be combined",
            hint="Use --json for full envelope.",
        )
        emit_failure(err, "items.export", 0, options)
        sys.exit(err.exit_code)
    if options.quiet:
        err = MutuallyExclusiveArgsError(
            "--quiet is not supported for export",
            hint="export writes raw content; --quiet has no key concept.",
        )
        emit_failure(err, "items.export", 0, options)
        sys.exit(err.exit_code)

    start = time.perf_counter()
    try:
        profile = load_config(profile=options.profile, config_path=options.config_path)
        api = ZoteroAPI(profile)
        svc = ExportService(api)
        result = svc.export(export_format, collection=collection)
    except CLIError as err:
        elapsed = int((time.perf_counter() - start) * 1000)
        emit_failure(err, "items.export", elapsed, options)
        sys.exit(err.exit_code)
    elapsed = int((time.perf_counter() - start) * 1000)

    raw_bytes: bytes = result["data"]
    byte_size = len(raw_bytes)

    if options.json_mode:
        env = Envelope.success(
            data={"format": export_format, "content": raw_bytes.decode("utf-8", errors="replace"), "byte_size": byte_size},
            command="items.export", elapsed_ms=elapsed,
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
