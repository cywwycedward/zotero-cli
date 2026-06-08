"""Config TOML I/O + path detection. The ONLY layer allowed to touch
~/.config/zotero-cli/config.toml and to autodetect the Zotero SQLite location.

Per DEVELOPMENT.md §5.2: services/ cannot do file I/O. config_service.py imports
this module to delegate all read/write/permission/path-detection work.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any, TypeAlias

import tomli_w

from zotero_cli.models.errors import ConfigInvalidError, ConfigNotFoundError

# Explicit alias: see DEVELOPMENT.md §5.2 adapter boundary note.
RawTomlDocument: TypeAlias = dict[str, Any]


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "zotero-cli" / "config.toml"


def read_toml(path: Path) -> RawTomlDocument:
    if not path.exists():
        raise ConfigNotFoundError(
            f"Config file not found: {path}",
            hint="Run 'zotero-cli config init' to create one.",
        )
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigInvalidError(f"Failed to parse {path}: {e}", cause=e) from e


def write_toml(path: Path, data: RawTomlDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tomli_w.dumps(dict(data)).encode("utf-8"))
    path.chmod(0o600)  # design §5.1


def detect_sqlite_db(env_override: str | None = None) -> str | None:
    """Find zotero.sqlite per design §5.4 priority:
    1. env_override (caller-supplied)
    2. ZOTERO_DATA_DIR env var
    3. Platform defaults (Linux/macOS ~/Zotero, Windows, Snap, Flatpak)
    """
    candidates: list[Path] = []
    if env_override:
        candidates.append(Path(env_override) / "zotero.sqlite")
    if env := os.environ.get("ZOTERO_DATA_DIR"):
        candidates.append(Path(env) / "zotero.sqlite")
    home = Path.home()
    if sys.platform == "win32":
        candidates.append(home / "Zotero" / "zotero.sqlite")
    else:
        candidates.append(home / "Zotero" / "zotero.sqlite")
        # Linux Snap
        candidates.append(home / "snap" / "zotero-snap" / "common" / "Zotero" / "zotero.sqlite")
        # Linux Flatpak
        candidates.append(
            home / ".var" / "app" / "org.zotero.Zotero" / "data" / "Zotero" / "zotero.sqlite"
        )
    for p in candidates:
        if p.exists():
            return str(p)
    return None
