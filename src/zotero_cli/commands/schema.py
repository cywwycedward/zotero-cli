"""commands/schema.py — command tree introspection (design §6 schema row)."""
from __future__ import annotations

from typing import Annotated, Any

import typer

from zotero_cli.commands._runner import run_command
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

    if command_name:
        target = _extract_subcommand(root_app, command_name)
        run_command(
            command="schema", mode=OutputMode.JSON, options=ctx.obj,
            work=lambda: target,
        )
    else:
        run_command(
            command="schema", mode=OutputMode.JSON, options=ctx.obj,
            work=lambda: _build_command_tree(root_app),
        )


def _extract_subcommand(typer_app: Any, name: str) -> dict[str, Any]:
    """Extract subcommand info for a single command."""
    for group in typer_app.registered_groups:
        group_name = group.name or group.typer_instance.info.name
        if group_name == name:
            commands = []
            for c in group.typer_instance.registered_commands:
                commands.append({
                    "name": c.name or c.callback.__name__,
                    "help": c.help or "",
                })
            return {"name": name, "commands": commands}
    return {"name": name, "commands": [], "error": "not found"}


def _build_command_tree(typer_app: Any) -> dict[str, Any]:
    """Build a JSON-serializable command tree from a Typer app."""
    result: dict[str, Any] = {"name": typer_app.info.name or "root", "groups": []}

    for group in typer_app.registered_groups:
        group_name: str = group.name or group.typer_instance.info.name
        commands: list[dict[str, Any]] = []
        for c in group.typer_instance.registered_commands:
            commands.append({
                "name": c.name or c.callback.__name__,
                "help": c.help or "",
            })
        result["groups"].append({"name": group_name, "commands": commands})

    return result
