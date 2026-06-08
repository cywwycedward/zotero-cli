"""commands/items.py — item subcommands: list, search, show, create, update, delete.

Per DEVELOPMENT.md §5.2: all commands go through run_command for stdout/stderr split.
"""
from __future__ import annotations

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
