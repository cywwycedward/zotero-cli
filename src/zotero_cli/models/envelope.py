"""JSON envelope models per design §8. All --json output uses Envelope."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from zotero_cli.models.errors import CLIError


class ErrorObject(BaseModel):
    """Error object embedded in failed Envelope (design §8.5)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    category: str
    hint: str | None = None
    context: dict[str, Any] | None = None
    cause: str | None = None  # text only (exception repr), no nested object, easy for jq


class MetaObject(BaseModel):
    """Metadata for any envelope. Command + elapsed_ms required; everything else
    is command-specific (count, total, affected_keys, backend, etc)."""

    model_config = ConfigDict(extra="allow")

    command: str
    elapsed_ms: int = Field(ge=0)

    @field_validator("command")
    @classmethod
    def _validate_command(cls, v: str) -> str:
        if not v or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*", v):
            raise ValueError(
                f"command must be a non-empty word or dotted path "
                f"(e.g. 'schema' or 'items.list'), got: {v!r}"
            )
        return v


class Envelope(BaseModel):
    """Top-level JSON envelope. ok flag governs which of data/error is populated."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Any = None
    error: ErrorObject | None = None
    meta: MetaObject

    @model_validator(mode="after")
    def _consistency(self) -> Envelope:
        if self.ok and self.error is not None:
            raise ValueError("error must be None when ok=True")
        if not self.ok and self.data is not None:
            raise ValueError("data must be None when ok=False")
        return self

    @classmethod
    def success(
        cls,
        *,
        data: Any,
        command: str,
        elapsed_ms: int,
        meta_extra: dict[str, Any] | None = None,
    ) -> Envelope:
        meta = MetaObject(command=command, elapsed_ms=elapsed_ms, **(meta_extra or {}))
        return cls(ok=True, data=data, error=None, meta=meta)

    @classmethod
    def failure(
        cls,
        err: CLIError,
        *,
        command: str,
        elapsed_ms: int,
        meta_extra: dict[str, Any] | None = None,
    ) -> Envelope:
        error_obj = ErrorObject(
            code=err.code,
            message=err.message,
            category=err.category,
            hint=err.hint,
            context=err.context if err.context else None,
            cause=repr(err.cause) if err.cause is not None else None,
        )
        full_meta = {"exit_code": err.exit_code, **(meta_extra or {})}
        meta = MetaObject(command=command, elapsed_ms=elapsed_ms, **full_meta)
        return cls(ok=False, data=None, error=error_obj, meta=meta)
