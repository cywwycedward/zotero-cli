"""Tests for the output renderer module — kv, kv-list, tree, summary, yaml."""
from __future__ import annotations

import pytest
import yaml as _yaml

from zotero_cli.models.envelope import Envelope
from zotero_cli.models.errors import MutuallyExclusiveArgsError
from zotero_cli.utils.output import OutputMode, render


class TestRouter:
    """Routing logic: json_mode, quiet, error vs mode dispatch."""

    def test_json_mode_always_returns_envelope_json(self) -> None:
        env = Envelope.success(data={"key": "ABC"}, command="items.show", elapsed_ms=100)
        result = render(envelope=env, mode=OutputMode.KV, json_mode=True, quiet=False)
        expected = env.model_dump_json(indent=2) + "\n"
        assert result == expected

    def test_quiet_and_json_mutually_exclusive(self) -> None:
        env = Envelope.success(data={"key": "ABC"}, command="items.show", elapsed_ms=100)
        with pytest.raises(MutuallyExclusiveArgsError):
            render(envelope=env, mode=OutputMode.KV, json_mode=True, quiet=True)


class TestKvFormat:
    """KV output mode tests."""

    def test_simple_dict(self) -> None:
        env = Envelope.success(
            data={"name": "Alice", "age": "30"},
            command="items.show",
            elapsed_ms=100,
        )
        result = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        assert result == "name: Alice\nage: 30\n"

    def test_list_value_joined_with_semicolons(self) -> None:
        env = Envelope.success(
            data={"tags": ["a", "b", "c"]},
            command="items.show",
            elapsed_ms=100,
        )
        result = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        assert result == "tags: a; b; c\n"

    def test_none_value_renders_empty_string(self) -> None:
        env = Envelope.success(
            data={"name": "Alice", "bio": None},
            command="items.show",
            elapsed_ms=100,
        )
        result = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        assert result == "name: Alice\nbio: \n"

    def test_failure_kv_writes_error_to_returned_string_with_marker(self) -> None:
        from zotero_cli.models.errors import ItemNotFoundError

        err = ItemNotFoundError("Item not found", hint="try items list")
        env = Envelope.failure(err, command="items.show", elapsed_ms=50)
        result = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        assert "Error" in result
        assert "ITEM_NOT_FOUND" in result
        assert "try items list" in result
        assert "✗" in result


class TestKvList:
    """KV_LIST output mode tests."""

    def test_two_items_separated_by_blank_line(self) -> None:
        data = [
            {"key": "ABC", "title": "First"},
            {"key": "DEF", "title": "Second"},
        ]
        env = Envelope.success(data=data, command="items.list", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.KV_LIST, json_mode=False, quiet=False
        )
        assert result == "key: ABC\ntitle: First\n\nkey: DEF\ntitle: Second\n"

    def test_empty_list_returns_empty_string(self) -> None:
        env = Envelope.success(data=[], command="items.list", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.KV_LIST, json_mode=False, quiet=False
        )
        assert result == ""


class TestTree:
    """TREE output mode tests."""

    def test_simple_tree(self) -> None:
        data = {
            "name": "Root",
            "key": "ROOT",
            "items_count": 0,
            "children": [
                {
                    "name": "Child1",
                    "key": "C1",
                    "items_count": 5,
                    "children": [
                        {
                            "name": "Grandchild",
                            "key": "GC1",
                            "items_count": 2,
                            "children": [],
                        }
                    ],
                },
                {
                    "name": "Child2",
                    "key": "C2",
                    "items_count": 3,
                    "children": [],
                },
            ],
        }
        env = Envelope.success(data=data, command="collections.tree", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.TREE, json_mode=False, quiet=False
        )
        expected = "Root\n├── Child1\n│   └── Grandchild\n└── Child2\n"
        assert result == expected


class TestSummary:
    """SUMMARY output mode tests."""

    def test_create_success(self) -> None:
        data = {"successful": ["ABC", "DEF"], "failed": []}
        env = Envelope.success(data=data, command="items.create", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False
        )
        expected = "✓ Created 2 items:\n  ABC, DEF\n"
        assert result == expected

    def test_with_failures(self) -> None:
        data = {
            "successful": ["ABC"],
            "failed": [{"code": "INVALID_FIELD", "message": "Title is required"}],
        }
        env = Envelope.success(data=data, command="items.create", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False
        )
        expected = (
            "✓ Created 1 item:\n"
            "  ABC\n"
            "\n"
            "✗ 1 item failed:\n"
            "  INVALID_FIELD: Title is required\n"
        )
        assert result == expected

    def test_update_verb(self) -> None:
        data = {"successful": ["XYZ"], "failed": []}
        env = Envelope.success(data=data, command="items.update", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False
        )
        assert "Updated" in result

    def test_delete_verb(self) -> None:
        data = {"successful": ["XYZ"], "failed": []}
        env = Envelope.success(data=data, command="items.delete", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False
        )
        assert "Deleted" in result

    def test_attach_verb(self) -> None:
        data = {"successful": ["XYZ"], "failed": []}
        env = Envelope.success(data=data, command="items.attach", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False
        )
        assert "Attached" in result


class TestYaml:
    """YAML output mode tests."""

    def test_masks_api_key(self) -> None:
        data = {"api_key": "abcdef123456", "name": "test"}
        env = Envelope.success(data=data, command="config.show", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.YAML, json_mode=False, quiet=False
        )
        parsed = _yaml.safe_load(result)
        assert parsed["api_key"] == "abcd****"
        assert parsed["name"] == "test"

    def test_masks_password_in_nested_webdav(self) -> None:
        data = {
            "webdav": {
                "url": "http://example.com",
                "password": "secret123",
            }
        }
        env = Envelope.success(data=data, command="config.show", elapsed_ms=100)
        result = render(
            envelope=env, mode=OutputMode.YAML, json_mode=False, quiet=False
        )
        parsed = _yaml.safe_load(result)
        assert parsed["webdav"]["password"] == "****"
        assert parsed["webdav"]["url"] == "http://example.com"


class TestFieldFilter:
    """Field filter application tests."""

    def test_kv_filter_restricts_fields(self) -> None:
        data = {"key": "ABC", "title": "Hello", "date": "2023"}
        env = Envelope.success(data=data, command="items.show", elapsed_ms=100)
        result = render(
            envelope=env,
            mode=OutputMode.KV,
            json_mode=False,
            quiet=False,
            field_filter=["key", "date"],
        )
        assert "key: ABC" in result
        assert "date: 2023" in result
        assert "title" not in result

    def test_kv_filter_preserves_data_order(self) -> None:
        data = {"date": "2023", "title": "Hello", "key": "ABC"}
        env = Envelope.success(data=data, command="items.show", elapsed_ms=100)
        result = render(
            envelope=env,
            mode=OutputMode.KV,
            json_mode=False,
            quiet=False,
            field_filter=["key", "title"],
        )
        # Data order is: date, title, key. Filtered to key+title gives: title, key
        lines = result.strip().split("\n")
        assert lines[0].startswith("title:")
        assert lines[1].startswith("key:")

    def test_field_filter_ignored_in_json_mode(self) -> None:
        data = {"key": "ABC", "title": "Hello", "date": "2023"}
        env = Envelope.success(data=data, command="items.show", elapsed_ms=100)
        result = render(
            envelope=env,
            mode=OutputMode.JSON,
            json_mode=True,
            quiet=False,
            field_filter=["key"],
        )
        # json_mode renders the full envelope, ignoring field_filter
        assert "title" in result
        assert "date" in result
        assert "key" in result

    def test_field_filter_none_returns_all_fields(self) -> None:
        data = {"key": "ABC", "title": "Hello", "date": "2023"}
        env = Envelope.success(data=data, command="items.show", elapsed_ms=100)
        result = render(
            envelope=env,
            mode=OutputMode.KV,
            json_mode=False,
            quiet=False,
            field_filter=None,
        )
        assert "key: ABC" in result
        assert "title: Hello" in result
        assert "date: 2023" in result

    def test_kv_list_filter_restricts_fields(self) -> None:
        data = [
            {"key": "ABC", "title": "First", "date": "2023"},
            {"key": "DEF", "title": "Second", "date": "2024"},
        ]
        env = Envelope.success(data=data, command="items.list", elapsed_ms=100)
        result = render(
            envelope=env,
            mode=OutputMode.KV_LIST,
            json_mode=False,
            quiet=False,
            field_filter=["key"],
        )
        assert result == "key: ABC\n\nkey: DEF\n"
        assert "title" not in result
        assert "date" not in result


class TestDefaultError:
    """Default error rendering tests."""

    def test_error_rendering_format(self) -> None:
        from zotero_cli.models.errors import ItemNotFoundError

        err = ItemNotFoundError("Item not found", hint="try items list")
        env = Envelope.failure(err, command="items.show", elapsed_ms=50)
        result = render(
            envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False
        )
        expected = "✗ Error: ITEM_NOT_FOUND\n  Item not found\n\n  Hint: try items list\n"
        assert result == expected

    def test_error_without_hint(self) -> None:
        from zotero_cli.models.errors import ItemNotFoundError

        err = ItemNotFoundError("Item not found")
        env = Envelope.failure(err, command="items.show", elapsed_ms=50)
        result = render(
            envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False
        )
        expected = "✗ Error: ITEM_NOT_FOUND\n  Item not found\n"
        assert result == expected
