"""commands/feeds.py — feed subcommands: list, show, items."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.services.config_service import load_config
from zotero_cli.services.feed_service import FeedService
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="RSS feed operations")


def _invoke(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    work_fn: Any,
    *,
    field_filter: list[str] | None = None,
) -> None:
    options: GlobalOptions = ctx.obj
    captured_meta: dict[str, Any] = {}

    def runner_work() -> Any:
        data, meta_extra = work_fn()
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


def _get_svc(ctx: typer.Context) -> FeedService:
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    return FeedService.from_profile(profile)


@app.command("list")
def list_feeds(
    ctx: typer.Context,
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """List all RSS feed subscriptions."""
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    field_filter = None if all_fields else profile.feed_fields.list

    def work() -> tuple[Any, Any]:
        svc = FeedService.from_profile(profile)
        feeds = svc.list_feeds()
        data = [f.model_dump() for f in feeds]
        return data, {"count": len(data)}

    _invoke(ctx, "feeds.list", OutputMode.KV_LIST, work, field_filter=field_filter)


@app.command("show")
def show_feed(
    ctx: typer.Context,
    feed_id: Annotated[int, typer.Argument(help="Feed libraryID")],
) -> None:
    """Show details of a single feed."""

    def work() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        feeds = svc.list_feeds()
        match = next((f for f in feeds if f.feed_id == feed_id), None)
        if match is None:
            from zotero_cli.models.errors import FeedNotFoundError

            raise FeedNotFoundError(f"Feed {feed_id} not found")
        return match.model_dump(), None

    _invoke(ctx, "feeds.show", OutputMode.KV, work)


@app.command("items")
def feed_items(
    ctx: typer.Context,
    feed_id: Annotated[int, typer.Argument(help="Feed libraryID")],
    date_filter: Annotated[
        str | None, typer.Option("--date", help="Date filter: YYYY / YYYY-MM / YYYY-MM-DD / X..Y")
    ] = None,
    include_undated: Annotated[
        bool, typer.Option("--include-undated", help="Include items without dates")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", help="Max items")] = 100,
    all_fields: Annotated[bool, typer.Option("--all-fields", help="Show all fields")] = False,
) -> None:
    """List items from a feed, optionally filtered by date."""
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    field_filter = None if all_fields else profile.feed_item_fields.list

    def work() -> tuple[Any, Any]:
        svc = FeedService.from_profile(profile)
        items = svc.list_items(
            feed_id,
            date_filter=date_filter,
            include_undated=include_undated,
            limit=limit,
        )
        data = [it.model_dump() for it in items]
        return data, {"count": len(data)}

    _invoke(ctx, "feeds.items", OutputMode.KV_LIST, work, field_filter=field_filter)
