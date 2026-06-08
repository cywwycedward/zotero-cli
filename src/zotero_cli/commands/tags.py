"""commands/tags.py — tag subcommands with audit logging for write ops."""
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
from zotero_cli.services.config_service import load_config
from zotero_cli.services.tag_service import TagService
from zotero_cli.utils.audit_log import AuditEntry, write_entry
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Tag operations")


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


def _get_svc(ctx: typer.Context) -> TagService:
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    return TagService(ZoteroAPI(profile))


@app.command("list")
def list_tags(ctx: typer.Context) -> None:
    """List all tags."""
    def work() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.list()
        return result["data"], dict(result["meta_extra"])
    _invoke(ctx, "tags.list", OutputMode.KV_LIST, work)


@app.command("add")
def add_tag(
    ctx: typer.Context,
    tag: Annotated[str, typer.Argument(help="Tag name")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to tag")],
) -> None:
    """Add a tag to items."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.add(tag, list(item_keys))
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "tags.add", action,
                  args_for_audit={"tag": tag, "item_keys": item_keys})


@app.command("remove")
def remove_tag(
    ctx: typer.Context,
    tag: Annotated[str, typer.Argument(help="Tag name")],
    item_keys: Annotated[list[str], typer.Argument(help="Item keys to untag")],
) -> None:
    """Remove a tag from items."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.remove(tag, list(item_keys))
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "tags.remove", action,
                  args_for_audit={"tag": tag, "item_keys": item_keys})


@app.command("rename")
def rename_tag(
    ctx: typer.Context,
    old_tag: Annotated[str, typer.Argument(help="Old tag name")],
    new_tag: Annotated[str, typer.Argument(help="New tag name")],
) -> None:
    """Rename a tag across all items."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.rename(old_tag, new_tag)
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "tags.rename", action,
                  args_for_audit={"old_tag": old_tag, "new_tag": new_tag})


@app.command("delete")
def delete_tag(
    ctx: typer.Context,
    tag: Annotated[str, typer.Argument(help="Tag to delete entirely")],
) -> None:
    """Delete a tag entirely."""
    def action() -> tuple[Any, Any]:
        svc = _get_svc(ctx)
        result = svc.delete(tag)
        return result["data"], result["meta_extra"]
    _invoke_write(ctx, "tags.delete", action,
                  args_for_audit={"tag": tag})
