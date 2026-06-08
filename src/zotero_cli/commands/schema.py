"""commands/schema.py — command tree introspection (design §6 / §7.2 schema row).

All paths (success, --quiet rejection, --command not found) output JSON envelope
to stdout. stderr is always empty. json_mode is forced True per design §7.2.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer
from typer.main import get_command

from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Schema introspection")


@app.command("schema")
def schema_command(
    ctx: typer.Context,
    command_name: Annotated[
        str | None, typer.Option("--command", help="Show schema for a specific command")
    ] = None,
) -> None:
    """Output the command tree as JSON (always JSON envelope, design §7.2)."""
    from zotero_cli.cli import app as root_app

    options: GlobalOptions = ctx.obj
    options.json_mode = True

    click_app = get_command(root_app)

    if command_name:
        run_command(
            command="schema",
            mode=OutputMode.JSON,
            options=options,
            work=lambda: _resolve_command(click_app, command_name),
        )
    else:
        run_command(
            command="schema",
            mode=OutputMode.JSON,
            options=options,
            work=lambda: _build_command_tree(click_app),
        )


def _resolve_command(click_app: Any, name: str) -> dict[str, Any]:
    """Resolve a command by name, supporting dot-notation (e.g. 'items.list')."""
    commands = getattr(click_app, "commands", {})
    parts = name.split(".", 1)
    group_name = parts[0]

    group = commands.get(group_name)
    if group is None:
        from zotero_cli.models.errors import ItemNotFoundError

        raise ItemNotFoundError(
            f"Command group '{group_name}' not found",
            hint=f"Available groups: {', '.join(sorted(commands.keys()))}",
        )

    if len(parts) == 1:
        sub_commands = getattr(group, "commands", None)
        if sub_commands is not None:
            return _extract_group(group_name, group)
        return _extract_single_command(group_name, group)

    sub_name = parts[1]
    sub_commands = getattr(group, "commands", None)
    if sub_commands is None:
        from zotero_cli.models.errors import ItemNotFoundError

        raise ItemNotFoundError(
            f"'{group_name}' is not a command group, cannot resolve '{name}'",
        )

    cmd = sub_commands.get(sub_name)
    if cmd is None:
        from zotero_cli.models.errors import ItemNotFoundError

        available = ", ".join(sorted(sub_commands.keys()))
        raise ItemNotFoundError(
            f"Command '{sub_name}' not found in group '{group_name}'",
            hint=f"Available commands: {available}",
        )

    return _extract_single_command(f"{group_name}.{sub_name}", cmd)


def _extract_params(cmd: Any) -> list[dict[str, Any]]:
    """Extract parameter schema from a Click/Typer command."""
    params: list[dict[str, Any]] = []
    for p in getattr(cmd, "params", []):
        if p.name in ("ctx",):
            continue
        entry: dict[str, Any] = {
            "name": p.name,
            "type": p.type.name if hasattr(p.type, "name") else str(p.type),
            "required": p.required,
        }
        is_option = "Option" in type(p).__name__
        if is_option:
            entry["kind"] = "option"
            if hasattr(p, "opts") and p.opts:
                entry["opts"] = list(p.opts)
            if p.default is not None:
                entry["default"] = p.default
        else:
            entry["kind"] = "argument"
        if hasattr(p, "help") and p.help:
            entry["help"] = p.help
        params.append(entry)
    return params


def _extract_single_command(name: str, cmd: Any) -> dict[str, Any]:
    """Extract schema for a single command including parameters."""
    return {
        "name": name,
        "help": getattr(cmd, "help", "") or "",
        "params": _extract_params(cmd),
    }


def _extract_group(name: str, group: Any) -> dict[str, Any]:
    """Extract schema for a command group and all its subcommands."""
    sub_commands = getattr(group, "commands", {})
    commands: list[dict[str, Any]] = []
    for cmd_name in sorted(sub_commands):
        cmd = sub_commands[cmd_name]
        commands.append(
            {
                "name": cmd_name,
                "help": getattr(cmd, "help", "") or "",
                "params": _extract_params(cmd),
            }
        )
    return {"name": name, "commands": commands}


def _build_command_tree(click_app: Any) -> dict[str, Any]:
    """Build a JSON-serializable command tree from a Click/Typer app."""
    commands = getattr(click_app, "commands", {})
    groups: list[dict[str, Any]] = []

    for name in sorted(commands):
        cmd = commands[name]
        if hasattr(cmd, "commands"):
            groups.append(_extract_group(name, cmd))
        else:
            groups.append(_extract_single_command(name, cmd))

    return {"name": "zotero-cli", "groups": groups}
