"""commands/collections.py — collection subcommands."""
from typing import Annotated, Any, Callable

import typer

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.services.collection_service import CollectionService
from zotero_cli.services.config_service import load_config
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Collection operations")


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


def _get_svc(ctx: typer.Context) -> CollectionService:
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    return CollectionService(ZoteroAPI(profile))


@app.command("list")
def list_coll(ctx: typer.Context) -> None:
    """List collections as a tree."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.list()
        return result["data"], None
    _invoke(ctx, "collections.list", OutputMode.TREE, work)


@app.command("show")
def show_coll(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key")],
) -> None:
    """Show a single collection."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.show(key)
        return result["data"], None
    _invoke(ctx, "collections.show", OutputMode.KV, work)


@app.command("create")
def create_coll(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name", help="Collection name")],
    parent: Annotated[str | None, typer.Option("--parent", help="Parent collection key")] = None,
) -> None:
    """Create a new collection."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.create(name, parent)
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "collections.create", OutputMode.SUMMARY, work)


@app.command("delete")
def delete_coll(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key")],
) -> None:
    """Delete a collection."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.delete(key)
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "collections.delete", OutputMode.SUMMARY, work)


@app.command("add-items")
def add_items(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to add")],
) -> None:
    """Add items to a collection."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.add_items(collection_key, list(item_keys))
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "collections.add_items", OutputMode.SUMMARY, work)


@app.command("remove-items")
def remove_items(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to remove")],
) -> None:
    """Remove items from a collection."""
    def work() -> tuple[Any, dict[str, Any] | None]:
        svc = _get_svc(ctx)
        result = svc.remove_items(collection_key, list(item_keys))
        return result["data"], result["meta_extra"]  # type: ignore[return-value]
    _invoke(ctx, "collections.remove_items", OutputMode.SUMMARY, work)
