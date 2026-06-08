from __future__ import annotations

import json

import pytest

from zotero_cli.models.envelope import Envelope, ErrorObject, MetaObject
from zotero_cli.models.errors import ItemNotFoundError


class TestErrorObject:
    def test_required_fields(self) -> None:
        err = ErrorObject(
            code="ITEM_NOT_FOUND",
            message="Item ABC not found",
            category="user_error",
        )
        assert err.code == "ITEM_NOT_FOUND"
        assert err.message == "Item ABC not found"
        assert err.category == "user_error"
        assert err.hint is None
        assert err.context is None
        assert err.cause is None

    def test_optional_fields(self) -> None:
        err = ErrorObject(
            code="C",
            message="m",
            category="user_error",
            hint="try X",
            context={"k": "v"},
            cause="ValueError: inner",
        )
        assert err.hint == "try X"
        assert err.context == {"k": "v"}
        assert err.cause == "ValueError: inner"

    def test_serializes_to_json(self) -> None:
        err = ErrorObject(code="C", message="m", category="user_error")
        d = err.model_dump()
        assert d == {
            "code": "C",
            "message": "m",
            "category": "user_error",
            "hint": None,
            "context": None,
            "cause": None,
        }
        assert json.loads(err.model_dump_json()) == d


class TestMetaObject:
    def test_required_fields(self) -> None:
        meta = MetaObject(command="items.list", elapsed_ms=123)
        assert meta.command == "items.list"
        assert meta.elapsed_ms == 123

    def test_extra_fields_allowed(self) -> None:
        meta = MetaObject(
            command="items.list",
            elapsed_ms=456,
            count=2,
            total=247,
            library_id="12345678",
        )
        d = meta.model_dump()
        assert d["count"] == 2
        assert d["total"] == 247
        assert d["library_id"] == "12345678"

    def test_command_accepts_top_level(self) -> None:
        meta = MetaObject(command="schema", elapsed_ms=1)
        assert meta.command == "schema"

    def test_command_accepts_dotted(self) -> None:
        meta = MetaObject(command="items.list", elapsed_ms=1)
        assert meta.command == "items.list"

    def test_command_rejects_invalid_chars(self) -> None:
        with pytest.raises(ValueError):
            MetaObject(command="items list", elapsed_ms=1)
        with pytest.raises(ValueError):
            MetaObject(command="", elapsed_ms=1)

    def test_elapsed_ms_non_negative(self) -> None:
        with pytest.raises(ValueError):
            MetaObject(command="x.y", elapsed_ms=-1)


class TestEnvelope:
    def test_success_minimal(self) -> None:
        env = Envelope.success(
            data={"key": "ABC"},
            command="items.show",
            elapsed_ms=100,
        )
        assert env.ok is True
        assert env.data == {"key": "ABC"}
        assert env.error is None
        assert env.meta.command == "items.show"
        assert env.meta.elapsed_ms == 100

    def test_success_with_extra_meta(self) -> None:
        env = Envelope.success(
            data=[],
            command="items.list",
            elapsed_ms=10,
            meta_extra={"count": 0, "total": 0, "library_id": "12345"},
        )
        d = env.model_dump()
        assert d["meta"]["count"] == 0
        assert d["meta"]["library_id"] == "12345"

    def test_failure_from_cli_error(self) -> None:
        err = ItemNotFoundError(
            "Item ABC not found",
            hint="try items list",
            context={"key": "ABC"},
        )
        env = Envelope.failure(err, command="items.show", elapsed_ms=50)
        assert env.ok is False
        assert env.data is None
        assert env.error is not None
        assert env.error.code == "ITEM_NOT_FOUND"
        assert env.error.category == "user_error"
        assert env.error.message == "Item ABC not found"
        assert env.error.hint == "try items list"
        assert env.error.context == {"key": "ABC"}

    def test_failure_includes_exit_code_in_meta(self) -> None:
        err = ItemNotFoundError("nope")
        env = Envelope.failure(err, command="items.show", elapsed_ms=1)
        assert env.meta.model_dump()["exit_code"] == 1

    def test_ok_true_with_error_rejected(self) -> None:
        with pytest.raises(ValueError, match="error must be None when ok=True"):
            Envelope(
                ok=True,
                data={},
                error=ErrorObject(code="C", message="m", category="user_error"),
                meta=MetaObject(command="x.y", elapsed_ms=1),
            )

    def test_ok_false_with_data_rejected(self) -> None:
        with pytest.raises(ValueError, match="data must be None when ok=False"):
            Envelope(
                ok=False,
                data={"k": "v"},
                error=ErrorObject(code="C", message="m", category="user_error"),
                meta=MetaObject(command="x.y", elapsed_ms=1),
            )
