"""commands/collections.py — collection subcommands with audit logging."""
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
from zotero_cli.models.errors import CLIError
from zotero_cli.services.collection_service import CollectionService
from zotero_cli.services.config_service import load_config
from zotero_cli.utils.audit_log import AuditEntry, write_entry
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Collection operations")


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


def _invoke_write(
    ctx: typer.Context,
    command: str,
    action: Callable[..., tuple[Any, Any]],
    *,
    args_for_audit: dict[str, Any] | None = None,
) -> None:
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
    parent: Annotated[
        str | None, typer.Option("--parent", help="Parent collection key")
    ] = None,
) -> None:
    """Create a new collection."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.create(name, parent)
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "collections.create", action,
                  args_for_audit={"name": name, "parent": parent})


@app.command("delete")
def delete_coll(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key")],
) -> None:
    """Delete a collection."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.delete(key)
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "collections.delete", action,
                  args_for_audit={"key": key})


@app.command("add-items")
def add_items(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to add")],
) -> None:
    """Add items to a collection."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.add_items(collection_key, list(item_keys))
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "collections.add_items", action,
                  args_for_audit={"collection_key": collection_key, "item_keys": item_keys})


@app.command("remove-items")
def remove_items(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to remove")],
) -> None:
    """Remove items from a collection."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.remove_items(collection_key, list(item_keys))
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "collections.remove_items", action,
                  args_for_audit={"collection_key": collection_key, "item_keys": item_keys})
