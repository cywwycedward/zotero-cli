"""commands/tags.py — tag subcommands."""
from typing import Annotated, Any, Callable

import typer

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.services.config_service import load_config
from zotero_cli.services.tag_service import TagService
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Tag operations")


def _invoke(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    work: Callable[[], tuple[Any, dict[str, Any] | None]],
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
    )


def _get_svc(ctx: typer.Context) -> TagService:
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    return TagService(ZoteroAPI(profile))


@app.command("list")
def list_tags(ctx: typer.Context) -> None:
    """List all tags."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.list()
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "tags.list", OutputMode.KV_LIST, work)


@app.command("add")
def add_tag(
    ctx: typer.Context,
    tag: Annotated[str, typer.Argument(help="Tag name")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to tag")],
) -> None:
    """Add a tag to items."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.add(tag, list(item_keys))
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "tags.add", OutputMode.SUMMARY, work)


@app.command("remove")
def remove_tag(
    ctx: typer.Context,
    tag: Annotated[str, typer.Argument(help="Tag name")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to untag")],
) -> None:
    """Remove a tag from items."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.remove(tag, list(item_keys))
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "tags.remove", OutputMode.SUMMARY, work)


@app.command("delete")
def delete_tag(
    ctx: typer.Context,
    tag: Annotated[str, typer.Argument(help="Tag to delete entirely")],
) -> None:
    """Delete a tag entirely."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.delete(tag)
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "tags.delete", OutputMode.SUMMARY, work)
