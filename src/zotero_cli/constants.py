"""Project-wide constants. Module-only (no I/O, no business logic)."""

from __future__ import annotations

from typing import Final

AUDIT_LOG_ROTATE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB, 设计 §9.4
DEFAULT_PARALLEL_UPLOADS: Final[int] = 4  # WebDAV 并发上限, 设计 §10.4
