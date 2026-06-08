"""commands/config.py — config init, show, set, get, validate, profiles.

All commands go through commands._runner.run_command for stdout/stderr split
and error handling. No direct I/O except via adapters/config_store.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from zotero_cli.adapters.config_store import default_config_path, read_toml, write_toml
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.models.config import Config
from zotero_cli.models.errors import (
    ConfigInvalidError,
    InvalidFieldError,
)
from zotero_cli.services.config_service import load_config, validate_profile
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Manage zotero-cli configuration")


def _get_options(ctx: typer.Context) -> GlobalOptions:
    """Extract GlobalOptions from typer Context, with sensible defaults."""
    obj = ctx.ensure_object(dict) if ctx.obj is None else ctx.obj
    if isinstance(obj, GlobalOptions):
        return obj
    # Fallback for tests that don't set ctx.obj via callback
    return GlobalOptions()


# ── init ───────────────────────────────────────────────────────────────────

_DEFAULT_PROFILE_TEMPLATE: dict[str, Any] = {
    "api_key": "<your-api-key>",
    "library_id": "<your-library-id>",
    "library_type": "user",
}


@app.command("init")
def _init(
    ctx: typer.Context,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing config")
    ] = False,
) -> None:
    """Create a new config file with a default profile."""
    options = _get_options(ctx)

    def work() -> dict[str, Any]:
        path: Path = options.config_path or default_config_path()
        if path.exists() and not force:
            raise ConfigInvalidError(
                f"Config file already exists at {path}",
                hint="Use --force to overwrite.",
            )
        write_toml(path, {"default": dict(_DEFAULT_PROFILE_TEMPLATE)})
        return {"profile": "default", "created": True, "path": str(path)}

    run_command(command="config.init", mode=OutputMode.SUMMARY, options=options, work=work)


# ── show ───────────────────────────────────────────────────────────────────


@app.command("show")
def _show(ctx: typer.Context) -> None:
    """Display the current config (secrets masked)."""
    options = _get_options(ctx)

    def work() -> dict[str, Any]:
        cfg = load_config(
            profile=options.profile, config_path=options.config_path,
        )
        return cfg.model_dump()

    run_command(command="config.show", mode=OutputMode.YAML, options=options, work=work)


# ── set ────────────────────────────────────────────────────────────────────


@app.command("set")
def _set(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dot-path key, e.g. webdav.password")],
    value: Annotated[str, typer.Argument(help="Value to set")],
) -> None:
    """Set a config value (dot-path keys supported)."""
    options = _get_options(ctx)

    def work() -> dict[str, Any]:
        path: Path = options.config_path or default_config_path()
        raw = read_toml(path)
        if options.profile not in raw:
            from zotero_cli.models.errors import InvalidProfileError
            raise InvalidProfileError(
                f"Profile {options.profile!r} not found",
                hint="Run 'zotero-cli config init' first.",
            )

        profile_data = dict(raw[options.profile])
        _set_dotpath(profile_data, key, value)

        # Re-validate through Config model (triggers compat matrix)
        Config(profiles={options.profile: profile_data})  # type: ignore[dict-item]
        raw[options.profile] = profile_data
        write_toml(path, raw)
        return {"key": key, "profile": options.profile}

    run_command(command="config.set", mode=OutputMode.SUMMARY, options=options, work=work)


def _set_dotpath(data: dict[str, Any], dotpath: str, value: str) -> None:
    parts = dotpath.split(".")
    for part in parts[:-1]:
        if part not in data or not isinstance(data[part], dict):
            data[part] = {}
        data = data[part]
    leaf = parts[-1]
    # Detect list fields: split comma-separated values
    if leaf == "list" or (len(parts) > 1 and parts[-2] in ("item_fields", "feed_item_fields")):
        data[leaf] = [v.strip() for v in value.split(",") if v.strip()]
    else:
        data[leaf] = value


# ── get ────────────────────────────────────────────────────────────────────


_SENSITIVE_KEYS = {"api_key", "password"}


@app.command("get")
def _get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dot-path key, e.g. webdav.password")],
) -> None:
    """Get a single config value."""
    options = _get_options(ctx)

    def work() -> dict[str, str]:
        cfg = load_config(
            profile=options.profile, config_path=options.config_path,
        )
        raw = cfg.model_dump()
        value = _get_dotpath(raw, key)
        if value is None:
            raise InvalidFieldError(
                f"Config key not found: {key!r} in profile {options.profile!r}",
                hint="Use 'zotero-cli config show' to see available keys.",
            )
        display_value = _mask_if_sensitive(key, str(value))
        return {"key": key, "value": display_value}

    run_command(command="config.get", mode=OutputMode.KV, options=options, work=work)


def _get_dotpath(data: dict[str, Any], dotpath: str) -> Any:
    parts = dotpath.split(".")
    for part in parts:
        if isinstance(data, dict) and part in data:
            data = data[part]
        else:
            return None
    return data


def _mask_if_sensitive(dotpath: str, value: str) -> str:
    leaf = dotpath.rsplit(".", 1)[-1] if "." in dotpath else dotpath
    if leaf in _SENSITIVE_KEYS:
        if leaf == "api_key" and len(value) >= 4:
            return value[:4] + "****"
        return "****"
    return value


# ── validate ───────────────────────────────────────────────────────────────


@app.command("validate")
def _validate(ctx: typer.Context) -> None:
    """Validate the config file."""
    options = _get_options(ctx)

    def work() -> dict[str, Any]:
        validate_profile(
            profile=options.profile, config_path=options.config_path,
        )
        return {"profile": options.profile, "valid": True}

    run_command(
        command="config.validate", mode=OutputMode.KV, options=options, work=work,
    )


# ── profiles ───────────────────────────────────────────────────────────────


@app.command("profiles")
def _profiles(ctx: typer.Context) -> None:
    """List all configured profiles."""
    options = _get_options(ctx)

    def work() -> list[dict[str, str]]:
        path: Path = options.config_path or default_config_path()
        raw = read_toml(path)
        return [{"key": name, "name": name} for name in sorted(raw)]

    run_command(
        command="config.profiles", mode=OutputMode.KV_LIST, options=options, work=work,
    )
