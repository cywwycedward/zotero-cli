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

    if json_mode or mode == OutputMode.JSON:
        if quiet:
            raise MutuallyExclusiveArgsError(
                f"--quiet is not supported with {mode.value} output mode",
                hint="Remove --quiet for this command",
            )
        return envelope.model_dump_json(indent=2) + "\n"

    if not envelope.ok:
        return _render_default_error(envelope)

    if quiet:
        if mode in (OutputMode.YAML, OutputMode.JSON):
            raise MutuallyExclusiveArgsError(
                f"--quiet is not supported with {mode.value} output mode",
                hint="Remove --quiet for this command",
            )
        return _render_quiet(envelope)

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
    if isinstance(data, list):
        return "".join(_render_tree(node) for node in data)

    if not isinstance(data, dict):
        return str(data) + "\n"

    lines: list[str] = []

    def _format_node(node: dict[str, Any]) -> str:
        name = node.get("name", "")
        key = node.get("key", "")
        items_count = node.get("items_count")
        parts = [name]
        if key:
            parts.append(f"[{key}]")
        if items_count is not None:
            item_word = "item" if items_count == 1 else "items"
            parts.append(f"({items_count} {item_word})")
        return " ".join(parts)

    def _build(node: dict[str, Any], prefix: str) -> None:
        children = node.get("children", [])
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            lines.append(prefix + connector + _format_node(child))
            _build(child, prefix + ("    " if is_last else "│   "))

    lines.append(_format_node(data))
    _build(data, "")
    return "\n".join(lines) + "\n"


def _render_dry_run_preview(data: dict[str, Any], command: str) -> str:
    """Render dry-run preview for human output."""
    lines: list[str] = ["[dry run] No changes made.\n"]

    if "would_create" in data:
        items = data["would_create"]
        for item in items:
            title = item.get("title", "(untitled)")
            item_type = item.get("itemType", "item")
            lines.append(f"  Would create: {item_type} — {title}")

    if "would_update" in data:
        update = data["would_update"]
        key = update.get("key", "?")
        fields = [k for k in update if k != "key"]
        lines.append(f"  Would update: {key} — fields: {', '.join(fields)}")

    if "would_delete" in data:
        keys = data["would_delete"]
        lines.append(f"  Would delete: {', '.join(str(k) for k in keys)}")

    if "would_upload" in data:
        uploads = data["would_upload"]
        for u in uploads:
            if isinstance(u, dict):
                lines.append(f"  Would upload: {u.get('file', '?')} → {u.get('parent_key', '?')}")
            else:
                lines.append(f"  Would upload: {u}")

    lines.append("")
    return "\n".join(lines)


def _render_summary(data: Any, command: str) -> str:
    """Render a summary of successful and failed operations."""
    if not isinstance(data, dict):
        return ""

    if data.get("dry_run"):
        return _render_dry_run_preview(data, command)

    successful = data.get("successful", data.get("uploaded", []))
    failed = data.get("failed", [])
    lines: list[str] = []

    verb = _determine_verb(command)

    if successful:
        count = len(successful)
        item_word = "item" if count == 1 else "items"
        keys = ", ".join(
            str(s.get("key") or s.get("attachment_key") or "") if isinstance(s, dict) else str(s)
            for s in successful
        )
        lines.append(f"✓ {verb} {count} {item_word}:")
        lines.append(f"  {keys}")
        parent_keys = {
            s["parent_item_key"]
            for s in successful
            if isinstance(s, dict) and "parent_item_key" in s
        }
        if parent_keys:
            lines.append(f"  parent: {', '.join(sorted(parent_keys))}")

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
    masked = mask_sensitive(data)
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


def _render_quiet(envelope: Envelope) -> str:
    """Render minimal key-only output for scripting."""
    data = envelope.data
    command = envelope.meta.command

    # Write operations: output affected_keys from meta
    if _is_write_operation(command):
        affected = getattr(envelope.meta, "affected_keys", None)
        if affected is None:
            return ""
        if not affected:
            return ""
        return "\n".join(str(k) for k in affected) + "\n"

    # List data with tree structure: collect keys from all root nodes
    if isinstance(data, list) and data and isinstance(data[0], dict) and "children" in data[0]:
        keys: list[str] = []
        for node in data:
            keys.extend(_collect_tree_keys(node))
        return "\n".join(keys) + "\n" if keys else ""

    # List data: output each item's key
    if isinstance(data, list):
        if not data:
            return ""
        return "\n".join(str(item["key"]) for item in data) + "\n"

    # Dict with children (tree data): collect keys from tree
    if isinstance(data, dict) and "children" in data:
        keys = _collect_tree_keys(data)
        return "\n".join(keys) + "\n"

    # Single dict: output its key
    if isinstance(data, dict) and "key" in data:
        return str(data["key"]) + "\n"

    return ""


# -- Helpers ---------------------------------------------------------------------------


def _apply_field_filter(data: Any, fields: list[str]) -> Any:
    """Restrict dict keys to those listed in *fields*, preserving data order."""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [_apply_field_filter(item, fields) for item in data]
    return data


def mask_sensitive(data: Any) -> Any:
    """Recursively mask sensitive fields (api_key, password)."""
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key == "api_key" and isinstance(value, str):
                result[key] = value[:4] + "****"
            elif key == "password" and isinstance(value, str):
                result[key] = "****"
            else:
                result[key] = mask_sensitive(value)
        return result
    return data


def _determine_verb(command: str) -> str:
    """Map command name to past-tense verb for summary output."""
    verb_map: dict[str, str] = {
        "items.create": "Created",
        "items.update": "Updated",
        "items.delete": "Deleted",
        "items.attach": "Attached",
        "items.add_doi": "Created",
        "collections.create": "Created",
        "collections.update": "Updated",
        "collections.delete": "Deleted",
        "collections.add_items": "Added items to",
        "collections.remove_items": "Removed items from",
        "tags.add": "Tagged",
        "tags.remove": "Untagged",
        "tags.rename": "Renamed",
        "tags.delete": "Deleted",
    }
    for prefix, verb in verb_map.items():
        if command.startswith(prefix):
            return verb
    return "Processed"


def _is_write_operation(command: str) -> bool:
    """Check if the command is a write operation that sets affected_keys."""
    write_prefixes = [
        "items.create",
        "items.update",
        "items.delete",
        "items.attach",
        "items.add_doi",
        "collections.create",
        "collections.update",
        "collections.delete",
        "collections.add_items",
        "collections.remove_items",
        "tags.add",
        "tags.remove",
        "tags.rename",
        "tags.delete",
    ]
    return any(command.startswith(p) for p in write_prefixes)


def _collect_tree_keys(data: dict[str, Any]) -> list[str]:
    """Collect all 'key' values from a tree structure."""
    keys: list[str] = []
    if "key" in data:
        keys.append(str(data["key"]))
    for child in data.get("children", []):
        keys.extend(_collect_tree_keys(child))
    return keys
