"""Output rendering for the CLI. Routes envelope data to format-specific renderers."""
from __future__ import annotations

import enum
from typing import Any

import yaml as _yaml

from zotero_cli.models.envelope import Envelope
from zotero_cli.models.errors import MutuallyExclusiveArgsError


class OutputMode(enum.StrEnum):
    KV = "kv"
    KV_LIST = "kv-list"
    TREE = "tree"
    SUMMARY = "summary"
    YAML = "yaml"
    JSON = "json"


# -- Public API ------------------------------------------------------------------------


def render(
    *,
    envelope: Envelope,
    mode: OutputMode,
    json_mode: bool,
    quiet: bool,
    field_filter: list[str] | None = None,
) -> str:
    """Route the envelope to the appropriate renderer based on mode and flags."""
    if json_mode and quiet:
        raise MutuallyExclusiveArgsError(
            "--json and --quiet are mutually exclusive",
            hint="Use one of --json or --quiet, not both",
        )

    if json_mode:
        return envelope.model_dump_json(indent=2) + "\n"

    if not envelope.ok:
        return _render_default_error(envelope)

    if quiet:
        return ""

    data = envelope.data

    if field_filter is not None and mode in (OutputMode.KV, OutputMode.KV_LIST):
        data = _apply_field_filter(data, field_filter)

    return _dispatch(data, envelope.meta.command, mode)


# -- Dispatch --------------------------------------------------------------------------


def _dispatch(data: Any, command: str, mode: OutputMode) -> str:
    """Dispatch to the correct renderer based on mode."""
    renderers = {
        OutputMode.KV: _render_kv,
        OutputMode.KV_LIST: _render_kv_list,
        OutputMode.TREE: _render_tree,
        OutputMode.SUMMARY: lambda d: _render_summary(d, command),
        OutputMode.YAML: _render_yaml,
    }
    renderer = renderers[mode]
    return renderer(data)


# -- Renderers -------------------------------------------------------------------------


def _render_kv(data: Any) -> str:
    """Render a dict as key: value lines."""
    if not isinstance(data, dict):
        return str(data) + "\n"
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            value_str = "; ".join(str(v) for v in value)
        elif value is None:
            value_str = ""
        else:
            value_str = str(value)
        lines.append(f"{key}: {value_str}")
    return "\n".join(lines) + "\n"


def _render_kv_list(data: Any) -> str:
    """Render a list of dicts as KV blocks separated by blank lines."""
    if not isinstance(data, list) or not data:
        return ""
    blocks: list[str] = []
    for item in data:
        blocks.append(_render_kv(item).rstrip("\n"))
    return "\n\n".join(blocks) + "\n"


def _render_tree(data: Any) -> str:
    """Render a nested dict with name/key/children as a unicode tree."""
    lines: list[str] = []

    def _build(node: dict[str, Any], prefix: str) -> None:
        children = node.get("children", [])
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            child_name = child.get("name", "")
            lines.append(prefix + connector + child_name)
            _build(child, prefix + ("    " if is_last else "│   "))

    root_name = data.get("name", "") if isinstance(data, dict) else str(data)
    lines.append(root_name)
    if isinstance(data, dict):
        _build(data, "")
    return "\n".join(lines) + "\n"


def _render_summary(data: Any, command: str) -> str:
    """Render a summary of successful and failed operations."""
    if not isinstance(data, dict):
        return ""

    successful = data.get("successful", [])
    failed = data.get("failed", [])
    lines: list[str] = []

    verb = _determine_verb(command)

    if successful:
        count = len(successful)
        item_word = "item" if count == 1 else "items"
        items_str = ", ".join(str(s) for s in successful)
        lines.append(f"✓ {verb} {count} {item_word}:")
        lines.append(f"  {items_str}")

    if failed:
        if successful:
            lines.append("")
        count = len(failed)
        item_word = "item" if count == 1 else "items"
        lines.append(f"✗ {count} {item_word} failed:")
        for item in failed:
            code = item.get("code", "UNKNOWN")
            message = item.get("message", "")
            lines.append(f"  {code}: {message}")

    if lines:
        lines.append("")
    return "\n".join(lines)


def _render_yaml(data: Any) -> str:
    """Render data as YAML with sensitive field masking."""
    masked = _mask_sensitive(data)
    return _yaml.safe_dump(masked, default_flow_style=False, allow_unicode=True)


def _render_default_error(envelope: Envelope) -> str:
    """Render a failed envelope as a user-facing error message."""
    error = envelope.error
    if error is None:
        return ""
    lines: list[str] = []
    lines.append(f"✗ Error: {error.code}")
    lines.append(f"  {error.message}")
    if error.hint:
        lines.append("")
        lines.append(f"  Hint: {error.hint}")
    return "\n".join(lines) + "\n"


# -- Helpers ---------------------------------------------------------------------------


def _apply_field_filter(data: Any, fields: list[str]) -> Any:
    """Restrict dict keys to those listed in *fields*, preserving data order."""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [_apply_field_filter(item, fields) for item in data]
    return data


def _mask_sensitive(data: Any) -> Any:
    """Recursively mask sensitive fields (api_key, password)."""
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key == "api_key" and isinstance(value, str):
                result[key] = value[:4] + "****"
            elif key == "password" and isinstance(value, str):
                result[key] = "****"
            else:
                result[key] = _mask_sensitive(value)
        return result
    return data


def _determine_verb(command: str) -> str:
    """Map command name to past-tense verb for summary output."""
    verb_map: dict[str, str] = {
        "items.create": "Created",
        "items.update": "Updated",
        "items.delete": "Deleted",
        "items.attach": "Attached",
    }
    for prefix, verb in verb_map.items():
        if command.startswith(prefix):
            return verb
    return "Processed"
