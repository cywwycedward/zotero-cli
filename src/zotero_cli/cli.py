"""Top-level Typer application. Thin entry: registers sub-commands and global flags."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from zotero_cli.commands._runner import GlobalOptions
from zotero_cli.commands.collections import app as collections_app
from zotero_cli.commands.config import app as config_app
from zotero_cli.commands.items import app as items_app
from zotero_cli.commands.tags import app as tags_app

app = typer.Typer(help="Single-user, agent-first CLI for Zotero")

app.add_typer(collections_app, name="collections")
app.add_typer(config_app, name="config")
app.add_typer(items_app, name="items")
app.add_typer(tags_app, name="tags")


@app.callback()
def _global(
    ctx: typer.Context,
    json_mode: Annotated[bool, typer.Option("--json", help="Output as JSON envelope")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Profile name")] = "default",
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Quiet mode: keys only")] = False,
    config_path: Annotated[Path | None, typer.Option("--config-path", hidden=True)] = None,
) -> None:
    ctx.obj = GlobalOptions(
        profile=profile,
        json_mode=json_mode,
        quiet=quiet,
        config_path=config_path,
    )
