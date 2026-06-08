# 阶段 1：基础设施 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**：搭好项目骨架并实现所有后续阶段都依赖的基础设施模块（错误模型、envelope、退出码、输出格式化、审计日志、日期解析），完成后无 CLI 命令但所有底层模块测试齐全、覆盖率达标。

**Architecture**：纯 Python 库，无外部 I/O 依赖（除 audit_log 写本地文件）。每个模块独立可测，遵循 DEVELOPMENT.md §5 分层（utils/ + models/）。严格 TDD：先写失败测试，再写最少实现。

**Tech Stack**：Python 3.11+ / uv / pydantic v2 / pytest + pytest-mock + respx / ruff + mypy strict。

**Source-of-truth references**：
- 设计文档：`docs/superpowers/specs/2026-06-07-zotero-cli-design.md`
- 协作规范：`DEVELOPMENT.md`
- 阶段验收 checklist：`DEVELOPMENT.md §9.1`

---

## 文件结构

```
zotero-cli/
├── pyproject.toml                        # uv 依赖 + ruff + mypy strict + pytest
├── README.md                             # 占位（阶段 6 完整化）
├── .gitignore
├── .python-version                       # 3.11
├── src/zotero_cli/
│   ├── __init__.py                       # __version__
│   ├── __main__.py                       # 占位
│   ├── constants.py                      # AUDIT_LOG_ROTATE_BYTES 等
│   ├── models/
│   │   ├── __init__.py
│   │   ├── errors.py                     # CLIError 基类 + 所有错误码子类 + from_code 注册表
│   │   └── envelope.py                   # ErrorObject / MetaObject / Envelope
│   └── utils/
│       ├── __init__.py
│       ├── exit_codes.py                 # 7 个退出码常量
│       ├── date_parser.py                # date_range_to_sql_bounds + 辅助
│       ├── output.py                     # render(data, mode, quiet, json) 路由
│       └── audit_log.py                  # write_entry + 自动轮转
└── tests/
    ├── __init__.py
    ├── conftest.py                       # 临时目录 fixture
    ├── unit/
    │   ├── __init__.py
    │   ├── test_errors.py
    │   ├── test_envelope.py
    │   ├── test_exit_codes.py
    │   ├── test_date_parser.py
    │   ├── test_output.py
    │   └── test_audit_log.py
    └── fixtures/
        └── __init__.py
```

## 模块依赖关系

```
exit_codes  ←  errors  ←  envelope
              ↑
              date_parser（仅依赖 errors.InvalidDateFormatError）
              audit_log（依赖 errors）
              output（依赖 envelope + errors）
```

**任务执行顺序**：Task 1 → 2 → 3 → 4 → 5 → 6 → 7-10（output）→ 11-13（audit_log）→ 14-17（date_parser）→ 18。
output 与 audit_log / date_parser 顺序可以互换（独立），但 envelope 必须在 output 前。

---

## Task 1: 项目骨架

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.python-version`
- Create: `README.md`（占位）
- Create: `src/zotero_cli/__init__.py`
- Create: `src/zotero_cli/__main__.py`
- Create: `src/zotero_cli/constants.py`
- Create: `src/zotero_cli/models/__init__.py`
- Create: `src/zotero_cli/utils/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/fixtures/__init__.py`

- [ ] **Step 1: 初始化 git（如果还没有）**

```bash
cd /path/to/zotero-cli
test -d .git || git init -b main
```

- [ ] **Step 2: 写 `pyproject.toml`**

```toml
[project]
name = "zotero-cli"
version = "0.1.0"
description = "Single-user, agent-first CLI for Zotero (literature management, PDF upload, RSS query)"
requires-python = ">=3.11"
readme = "README.md"
dependencies = [
    "typer[all]>=0.12.0",
    "pyzotero>=1.5.0",
    "webdav4>=0.10.0",
    "pydantic-settings>=2.2.0",
    "tomli-w>=1.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",
    "respx>=0.21",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-PyYAML>=6.0",
]
webdav-test = [
    "pytest-httpserver>=1.0",
    "wsgidav>=4.3",
]

[project.scripts]
zotero-cli = "zotero_cli.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/zotero_cli"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]

[tool.ruff.lint.isort]
known-first-party = ["zotero_cli"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
warn_redundant_casts = true

[[tool.mypy.overrides]]
module = ["pyzotero.*", "webdav4.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.coverage.run]
source = ["src/zotero_cli"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

- [ ] **Step 3: 写 `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
dist/
build/

# Caches
.ruff_cache/
.mypy_cache/
.pytest_cache/
.coverage
htmlcov/

# Project artifacts (DEVELOPMENT.md §10.5)
*.pdf
*.sqlite
*.sqlite-journal
audit.log*

# IDE
.idea/
.vscode/
*.swp
```

- [ ] **Step 4: 写 `.python-version`**

```
3.11
```

- [ ] **Step 5: 写 `README.md`（占位）**

```markdown
# zotero-cli

Single-user, agent-first CLI for Zotero. See `docs/superpowers/specs/2026-06-07-zotero-cli-design.md` for the design spec.

> 阶段 6 之前 README 仅占位。
```

- [ ] **Step 6: 写所有 `__init__.py` 与占位文件**

`src/zotero_cli/__init__.py`：

```python
__version__ = "0.1.0"
```

`src/zotero_cli/__main__.py`：

```python
def main() -> None:
    raise NotImplementedError("CLI entry implemented in 阶段 3")


if __name__ == "__main__":
    main()
```

`src/zotero_cli/constants.py`：

```python
"""Project-wide constants. Module-only (no I/O, no business logic)."""
from __future__ import annotations
from typing import Final

AUDIT_LOG_ROTATE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB, 设计 §9.4
DEFAULT_PARALLEL_UPLOADS: Final[int] = 4  # WebDAV 并发上限, 设计 §10.4
```

`src/zotero_cli/models/__init__.py`、`src/zotero_cli/utils/__init__.py`、`tests/__init__.py`、`tests/unit/__init__.py`、`tests/fixtures/__init__.py`：每个都是空文件（`touch` 即可）。

`tests/conftest.py`：

```python
"""Shared pytest fixtures for the whole project."""
from __future__ import annotations

import pytest


@pytest.fixture
def tmp_audit_log(tmp_path):
    """Fresh audit log path under pytest tmp_path; auto-cleaned."""
    return tmp_path / "audit.log"
```

- [ ] **Step 7: `uv sync` 装依赖**

Run：
```bash
uv sync --extra dev
```

Expected：成功安装所有依赖到 `.venv/`，`uv.lock` 生成。

- [ ] **Step 8: 烟雾测试**

Run：
```bash
uv run python -c "import zotero_cli; print(zotero_cli.__version__)"
uv run ruff check src tests
uv run mypy src
uv run pytest --collect-only
```

Expected：
- 第 1 行打印 `0.1.0`
- ruff：no issues
- mypy：Success: no issues found in N source files
- pytest：collected 0 items（暂无测试，正常）

- [ ] **Step 9: 首次 commit**

```bash
git add pyproject.toml .gitignore .python-version README.md src tests uv.lock
git commit -m "chore: initialize project skeleton with uv + ruff + mypy strict"
```

---

## Task 2: utils/exit_codes.py

**Files:**
- Create: `src/zotero_cli/utils/exit_codes.py`
- Test: `tests/unit/test_exit_codes.py`

设计 §9.1 退出码表：0 / 1 / 2 / 3 / 4 / 64 / 130。

- [ ] **Step 1: 写失败测试**

`tests/unit/test_exit_codes.py`：

```python
from zotero_cli.utils import exit_codes


def test_success_is_zero() -> None:
    assert exit_codes.EXIT_SUCCESS == 0


def test_user_error_is_one() -> None:
    assert exit_codes.EXIT_USER_ERROR == 1


def test_network_error_is_two() -> None:
    assert exit_codes.EXIT_NETWORK_ERROR == 2


def test_auth_error_is_three() -> None:
    assert exit_codes.EXIT_AUTH_ERROR == 3


def test_local_error_is_four() -> None:
    assert exit_codes.EXIT_LOCAL_ERROR == 4


def test_usage_error_is_64() -> None:
    assert exit_codes.EXIT_USAGE_ERROR == 64


def test_interrupted_is_130() -> None:
    assert exit_codes.EXIT_INTERRUPTED == 130
```

- [ ] **Step 2: 跑测试确认全部失败**

Run：`uv run pytest tests/unit/test_exit_codes.py -v`
Expected：7 个失败，错误为 `AttributeError: module 'zotero_cli.utils.exit_codes' has no attribute ...`

- [ ] **Step 3: 写实现**

`src/zotero_cli/utils/exit_codes.py`：

```python
"""CLI exit codes per design §9.1.

These constants are used by:
- CLIError subclasses (models/errors.py) to set exit_code
- commands/* outermost handler to call sys.exit(...)
"""
from __future__ import annotations
from typing import Final

EXIT_SUCCESS: Final[int] = 0
EXIT_USER_ERROR: Final[int] = 1
EXIT_NETWORK_ERROR: Final[int] = 2
EXIT_AUTH_ERROR: Final[int] = 3
EXIT_LOCAL_ERROR: Final[int] = 4
EXIT_USAGE_ERROR: Final[int] = 64
EXIT_INTERRUPTED: Final[int] = 130
```

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest tests/unit/test_exit_codes.py -v`
Expected：7 passed

- [ ] **Step 5: lint + type check**

Run：
```bash
uv run ruff check src tests
uv run mypy src
```
Expected：双 clean。

- [ ] **Step 6: commit**

```bash
git add src/zotero_cli/utils/exit_codes.py tests/unit/test_exit_codes.py
git commit -m "feat(exit_codes): define CLI exit code constants per design §9.1"
```

---

## Task 3: models/errors.py — CLIError 基类

**Files:**
- Create: `src/zotero_cli/models/errors.py`
- Test: `tests/unit/test_errors.py`

CLIError 是所有 CLI 错误的基类，子类只覆盖 `code` / `category` / `exit_code` 类属性。

- [ ] **Step 1: 写失败测试**

`tests/unit/test_errors.py`：

```python
from __future__ import annotations

import pytest

from zotero_cli.models.errors import CLIError
from zotero_cli.utils.exit_codes import EXIT_USER_ERROR


class TestCLIErrorBase:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(CLIError, Exception)

    def test_default_attrs(self) -> None:
        err = CLIError("something went wrong")
        assert err.message == "something went wrong"
        assert err.code == "GENERIC"
        assert err.category == "user_error"
        assert err.exit_code == EXIT_USER_ERROR
        assert err.hint is None
        assert err.context == {}
        assert err.cause is None

    def test_keyword_overrides(self) -> None:
        cause = ValueError("inner")
        err = CLIError(
            "msg",
            hint="try X",
            context={"key": "value"},
            cause=cause,
        )
        assert err.hint == "try X"
        assert err.context == {"key": "value"}
        assert err.cause is cause

    def test_str_returns_message(self) -> None:
        err = CLIError("readable message")
        assert str(err) == "readable message"

    def test_subclass_inherits_class_attrs(self) -> None:
        class FakeAuthError(CLIError):
            code = "FAKE_AUTH"
            category = "auth_error"
            exit_code = 3

        err = FakeAuthError("nope")
        assert err.code == "FAKE_AUTH"
        assert err.category == "auth_error"
        assert err.exit_code == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest tests/unit/test_errors.py -v`
Expected：5 failed，错误为 `ImportError: cannot import name 'CLIError' from 'zotero_cli.models.errors'`

- [ ] **Step 3: 写实现**

`src/zotero_cli/models/errors.py`：

```python
"""CLI error hierarchy. All raised exceptions in zotero-cli must subclass CLIError.

Per DEVELOPMENT.md §4.3 (error flow): adapters translate external library exceptions
into CLIError subclasses; services don't wrap; commands render Envelope and exit().

Per design §9.2: every error code maps to exactly one subclass.
"""
from __future__ import annotations

from typing import Any, Literal

from zotero_cli.utils.exit_codes import (
    EXIT_AUTH_ERROR,
    EXIT_LOCAL_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_USAGE_ERROR,
    EXIT_USER_ERROR,
)

ErrorCategory = Literal[
    "user_error",
    "network_error",
    "auth_error",
    "local_error",
    "usage_error",
]


class CLIError(Exception):
    """Base class for all CLI-raised errors. Subclasses override class attrs."""

    code: str = "GENERIC"
    category: ErrorCategory = "user_error"
    exit_code: int = EXIT_USER_ERROR

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.context = context if context is not None else {}
        self.cause = cause
```

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest tests/unit/test_errors.py -v`
Expected：5 passed

- [ ] **Step 5: lint + type check + commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/models/errors.py tests/unit/test_errors.py
git commit -m "feat(errors): add CLIError base class with code/category/exit_code attrs"
```

---

## Task 4: models/errors.py — 所有错误码子类 + from_code 注册表

**Files:**
- Modify: `src/zotero_cli/models/errors.py`
- Modify: `tests/unit/test_errors.py`

按设计 §9.2 把所有错误码列出。每个子类只覆盖 `code` / `category` / `exit_code`。`from_code()` 是注册表查找函数，给 adapter 层翻译异常时按 code 字符串查类。

错误码全集（按类别分组）：

- **user_error (1)**：`ITEM_NOT_FOUND`, `COLLECTION_NOT_FOUND`, `TAG_NOT_FOUND`, `FEED_NOT_FOUND`, `INVALID_ITEM_TYPE`, `INVALID_DATE_FORMAT`, `INVALID_FIELD`, `MISSING_REQUIRED_ARG`, `FILE_NOT_FOUND`, `INVALID_PROFILE`, `UNSUPPORTED_LIBRARY_TYPE`
- **network_error (2)**：`API_TIMEOUT`, `API_RATE_LIMIT`, `API_SERVER_ERROR`, `WEBDAV_TIMEOUT`, `WEBDAV_CONNECTION_ERROR`, `NETWORK_ERROR`, `STORAGE_QUOTA_EXCEEDED`
- **auth_error (3)**：`INVALID_API_KEY`, `INSUFFICIENT_PERMISSIONS`, `WEBDAV_AUTH_FAILED`
- **local_error (4)**：`SQLITE_NOT_FOUND`, `SQLITE_LOCKED`, `SQLITE_SCHEMA_INCOMPATIBLE`, `CONFIG_NOT_FOUND`, `CONFIG_INVALID`, `AUDIT_LOG_WRITE_FAILED`, `WEBDAV_FILE_EXISTS`, `WEBDAV_PROP_INVALID`, `MD5_MISMATCH`
- **usage_error (64)**：`USAGE_ERROR`, `MUTUALLY_EXCLUSIVE_ARGS`

- [ ] **Step 1: 写失败测试（参数化覆盖所有子类）**

追加到 `tests/unit/test_errors.py`：

```python
from zotero_cli.models.errors import (
    # user_error
    ItemNotFoundError, CollectionNotFoundError, TagNotFoundError, FeedNotFoundError,
    InvalidItemTypeError, InvalidDateFormatError, InvalidFieldError,
    MissingRequiredArgError, FileNotFoundCLIError, InvalidProfileError,
    UnsupportedLibraryTypeError,
    # network_error
    ApiTimeoutError, ApiRateLimitError, ApiServerError, WebdavTimeoutError,
    WebdavConnectionError, NetworkError, StorageQuotaExceededError,
    # auth_error
    InvalidApiKeyError, InsufficientPermissionsError, WebdavAuthFailedError,
    # local_error
    SqliteNotFoundError, SqliteLockedError, SqliteSchemaIncompatibleError,
    ConfigNotFoundError, ConfigInvalidError, AuditLogWriteFailedError,
    WebdavFileExistsError, WebdavPropInvalidError, Md5MismatchError,
    # usage_error
    UsageError, MutuallyExclusiveArgsError,
    from_code,
)


USER_ERROR_CASES = [
    (ItemNotFoundError, "ITEM_NOT_FOUND"),
    (CollectionNotFoundError, "COLLECTION_NOT_FOUND"),
    (TagNotFoundError, "TAG_NOT_FOUND"),
    (FeedNotFoundError, "FEED_NOT_FOUND"),
    (InvalidItemTypeError, "INVALID_ITEM_TYPE"),
    (InvalidDateFormatError, "INVALID_DATE_FORMAT"),
    (InvalidFieldError, "INVALID_FIELD"),
    (MissingRequiredArgError, "MISSING_REQUIRED_ARG"),
    (FileNotFoundCLIError, "FILE_NOT_FOUND"),
    (InvalidProfileError, "INVALID_PROFILE"),
    (UnsupportedLibraryTypeError, "UNSUPPORTED_LIBRARY_TYPE"),
]
NETWORK_ERROR_CASES = [
    (ApiTimeoutError, "API_TIMEOUT"),
    (ApiRateLimitError, "API_RATE_LIMIT"),
    (ApiServerError, "API_SERVER_ERROR"),
    (WebdavTimeoutError, "WEBDAV_TIMEOUT"),
    (WebdavConnectionError, "WEBDAV_CONNECTION_ERROR"),
    (NetworkError, "NETWORK_ERROR"),
    (StorageQuotaExceededError, "STORAGE_QUOTA_EXCEEDED"),
]
AUTH_ERROR_CASES = [
    (InvalidApiKeyError, "INVALID_API_KEY"),
    (InsufficientPermissionsError, "INSUFFICIENT_PERMISSIONS"),
    (WebdavAuthFailedError, "WEBDAV_AUTH_FAILED"),
]
LOCAL_ERROR_CASES = [
    (SqliteNotFoundError, "SQLITE_NOT_FOUND"),
    (SqliteLockedError, "SQLITE_LOCKED"),
    (SqliteSchemaIncompatibleError, "SQLITE_SCHEMA_INCOMPATIBLE"),
    (ConfigNotFoundError, "CONFIG_NOT_FOUND"),
    (ConfigInvalidError, "CONFIG_INVALID"),
    (AuditLogWriteFailedError, "AUDIT_LOG_WRITE_FAILED"),
    (WebdavFileExistsError, "WEBDAV_FILE_EXISTS"),
    (WebdavPropInvalidError, "WEBDAV_PROP_INVALID"),
    (Md5MismatchError, "MD5_MISMATCH"),
]
USAGE_ERROR_CASES = [
    (UsageError, "USAGE_ERROR"),
    (MutuallyExclusiveArgsError, "MUTUALLY_EXCLUSIVE_ARGS"),
]


@pytest.mark.parametrize("cls,code", USER_ERROR_CASES)
def test_user_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "user_error"
    assert err.exit_code == 1


@pytest.mark.parametrize("cls,code", NETWORK_ERROR_CASES)
def test_network_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "network_error"
    assert err.exit_code == 2


@pytest.mark.parametrize("cls,code", AUTH_ERROR_CASES)
def test_auth_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "auth_error"
    assert err.exit_code == 3


@pytest.mark.parametrize("cls,code", LOCAL_ERROR_CASES)
def test_local_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "local_error"
    assert err.exit_code == 4


@pytest.mark.parametrize("cls,code", USAGE_ERROR_CASES)
def test_usage_errors(cls: type[CLIError], code: str) -> None:
    err = cls("msg")
    assert err.code == code
    assert err.category == "usage_error"
    assert err.exit_code == 64


class TestFromCode:
    def test_returns_correct_class(self) -> None:
        err = from_code("ITEM_NOT_FOUND", "item missing")
        assert isinstance(err, ItemNotFoundError)
        assert err.message == "item missing"

    def test_passes_kwargs(self) -> None:
        err = from_code("ITEM_NOT_FOUND", "msg", hint="try X", context={"k": "v"})
        assert err.hint == "try X"
        assert err.context == {"k": "v"}

    def test_unknown_code_falls_back_to_cli_error(self) -> None:
        err = from_code("DEFINITELY_NOT_REAL", "msg")
        assert type(err) is CLIError
        assert err.code == "DEFINITELY_NOT_REAL"
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest tests/unit/test_errors.py -v`
Expected：30 多个 ImportError。

- [ ] **Step 3: 写实现 — 追加到 `src/zotero_cli/models/errors.py`**

```python
# user_error (1)
class ItemNotFoundError(CLIError):
    code = "ITEM_NOT_FOUND"

class CollectionNotFoundError(CLIError):
    code = "COLLECTION_NOT_FOUND"

class TagNotFoundError(CLIError):
    code = "TAG_NOT_FOUND"

class FeedNotFoundError(CLIError):
    code = "FEED_NOT_FOUND"

class InvalidItemTypeError(CLIError):
    code = "INVALID_ITEM_TYPE"

class InvalidDateFormatError(CLIError):
    code = "INVALID_DATE_FORMAT"

class InvalidFieldError(CLIError):
    code = "INVALID_FIELD"

class MissingRequiredArgError(CLIError):
    code = "MISSING_REQUIRED_ARG"

class FileNotFoundCLIError(CLIError):
    code = "FILE_NOT_FOUND"

class InvalidProfileError(CLIError):
    code = "INVALID_PROFILE"

class UnsupportedLibraryTypeError(CLIError):
    code = "UNSUPPORTED_LIBRARY_TYPE"


# network_error (2)
class _NetworkError(CLIError):
    category = "network_error"
    exit_code = EXIT_NETWORK_ERROR

class ApiTimeoutError(_NetworkError):
    code = "API_TIMEOUT"

class ApiRateLimitError(_NetworkError):
    code = "API_RATE_LIMIT"

class ApiServerError(_NetworkError):
    code = "API_SERVER_ERROR"

class WebdavTimeoutError(_NetworkError):
    code = "WEBDAV_TIMEOUT"

class WebdavConnectionError(_NetworkError):
    code = "WEBDAV_CONNECTION_ERROR"

class NetworkError(_NetworkError):
    code = "NETWORK_ERROR"

class StorageQuotaExceededError(_NetworkError):
    code = "STORAGE_QUOTA_EXCEEDED"


# auth_error (3)
class _AuthError(CLIError):
    category = "auth_error"
    exit_code = EXIT_AUTH_ERROR

class InvalidApiKeyError(_AuthError):
    code = "INVALID_API_KEY"

class InsufficientPermissionsError(_AuthError):
    code = "INSUFFICIENT_PERMISSIONS"

class WebdavAuthFailedError(_AuthError):
    code = "WEBDAV_AUTH_FAILED"


# local_error (4)
class _LocalError(CLIError):
    category = "local_error"
    exit_code = EXIT_LOCAL_ERROR

class SqliteNotFoundError(_LocalError):
    code = "SQLITE_NOT_FOUND"

class SqliteLockedError(_LocalError):
    code = "SQLITE_LOCKED"

class SqliteSchemaIncompatibleError(_LocalError):
    code = "SQLITE_SCHEMA_INCOMPATIBLE"

class ConfigNotFoundError(_LocalError):
    code = "CONFIG_NOT_FOUND"

class ConfigInvalidError(_LocalError):
    code = "CONFIG_INVALID"

class AuditLogWriteFailedError(_LocalError):
    code = "AUDIT_LOG_WRITE_FAILED"

class WebdavFileExistsError(_LocalError):
    code = "WEBDAV_FILE_EXISTS"

class WebdavPropInvalidError(_LocalError):
    code = "WEBDAV_PROP_INVALID"

class Md5MismatchError(_LocalError):
    code = "MD5_MISMATCH"


# usage_error (64)
class _UsageError(CLIError):
    category = "usage_error"
    exit_code = EXIT_USAGE_ERROR

class UsageError(_UsageError):
    code = "USAGE_ERROR"

class MutuallyExclusiveArgsError(_UsageError):
    code = "MUTUALLY_EXCLUSIVE_ARGS"


# 注册表
_REGISTRY: dict[str, type[CLIError]] = {
    cls.code: cls
    for cls in [
        ItemNotFoundError, CollectionNotFoundError, TagNotFoundError, FeedNotFoundError,
        InvalidItemTypeError, InvalidDateFormatError, InvalidFieldError,
        MissingRequiredArgError, FileNotFoundCLIError, InvalidProfileError,
        UnsupportedLibraryTypeError,
        ApiTimeoutError, ApiRateLimitError, ApiServerError, WebdavTimeoutError,
        WebdavConnectionError, NetworkError, StorageQuotaExceededError,
        InvalidApiKeyError, InsufficientPermissionsError, WebdavAuthFailedError,
        SqliteNotFoundError, SqliteLockedError, SqliteSchemaIncompatibleError,
        ConfigNotFoundError, ConfigInvalidError, AuditLogWriteFailedError,
        WebdavFileExistsError, WebdavPropInvalidError, Md5MismatchError,
        UsageError, MutuallyExclusiveArgsError,
    ]
}


def from_code(code: str, message: str, **kwargs: Any) -> CLIError:
    """Look up CLI error class by code string. Falls back to bare CLIError with
    custom code if unknown — used by adapters when external libs return new error
    codes we haven't classified yet."""
    cls = _REGISTRY.get(code)
    if cls is None:
        err = CLIError(message, **kwargs)
        err.code = code
        return err
    return cls(message, **kwargs)
```

- [ ] **Step 4: 跑测试确认通过**

Run：`uv run pytest tests/unit/test_errors.py -v`
Expected：38 passed（5 base + 11 user + 7 network + 3 auth + 8 local + 2 usage + 3 from_code）

- [ ] **Step 5: lint + type check + commit**

```bash
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/models/errors.py tests/unit/test_errors.py
git commit -m "feat(errors): add all error code subclasses + from_code registry per design §9.2"
```

---

## Task 5: models/envelope.py — ErrorObject + MetaObject

**Files:**
- Create: `src/zotero_cli/models/envelope.py`
- Test: `tests/unit/test_envelope.py`

设计 §8.5 ErrorObject schema、§8.1 MetaObject 字段。MetaObject 字段多变（不同命令有不同字段：list 有 count/total/limit；写操作有 affected_keys；附件有 backend），用 pydantic 的 `extra="allow"` + 必填核心字段。

- [ ] **Step 1: 写失败测试**

`tests/unit/test_envelope.py`：

```python
from __future__ import annotations

import json

import pytest

from zotero_cli.models.envelope import ErrorObject, MetaObject


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
            "code": "C", "message": "m", "category": "user_error",
            "hint": None, "context": None, "cause": None,
        }
        assert json.loads(err.model_dump_json()) == d


class TestMetaObject:
    def test_required_fields(self) -> None:
        meta = MetaObject(command="items.list", elapsed_ms=123)
        assert meta.command == "items.list"
        assert meta.elapsed_ms == 123

    def test_extra_fields_allowed(self) -> None:
        # MetaObject 必须接受任意命令特有字段（count / affected_keys / backend / etc）
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
        # 顶级命令（如 schema）合法
        meta = MetaObject(command="schema", elapsed_ms=1)
        assert meta.command == "schema"

    def test_command_accepts_dotted(self) -> None:
        meta = MetaObject(command="items.list", elapsed_ms=1)
        assert meta.command == "items.list"

    def test_command_rejects_invalid_chars(self) -> None:
        with pytest.raises(ValueError):
            MetaObject(command="items list", elapsed_ms=1)  # 空格不允许
        with pytest.raises(ValueError):
            MetaObject(command="", elapsed_ms=1)  # 空字符串不允许

    def test_elapsed_ms_non_negative(self) -> None:
        with pytest.raises(ValueError):
            MetaObject(command="x.y", elapsed_ms=-1)
```

- [ ] **Step 2: 跑测试确认失败**

Run：`uv run pytest tests/unit/test_envelope.py -v`
Expected：所有 ImportError（envelope 还没建）。

- [ ] **Step 3: 写实现**

`src/zotero_cli/models/envelope.py`：

```python
"""JSON envelope models per design §8. All --json output uses Envelope."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorObject(BaseModel):
    """Error object embedded in failed Envelope (design §8.5)."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    category: str
    hint: str | None = None
    context: dict[str, Any] | None = None
    cause: str | None = None  # 仅文本（异常 repr），不嵌套对象，方便 jq 处理


class MetaObject(BaseModel):
    """Metadata for any envelope. Command + elapsed_ms required; everything else
    is command-specific (count, total, affected_keys, backend, etc)."""

    model_config = ConfigDict(extra="allow")

    command: str
    elapsed_ms: int = Field(ge=0)

    @field_validator("command")
    @classmethod
    def _validate_command(cls, v: str) -> str:
        # 允许 "schema" 顶级命令或 "items.list" 形式；只校验字符集（无空格、非空、word + 点）
        import re
        if not v or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*", v):
            raise ValueError(
                f"command must be a non-empty word or dotted path "
                f"(e.g. 'schema' or 'items.list'), got: {v!r}"
            )
        return v
```

- [ ] **Step 4: 跑测试 + commit**

```bash
uv run pytest tests/unit/test_envelope.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/models/envelope.py tests/unit/test_envelope.py
git commit -m "feat(envelope): add ErrorObject and MetaObject pydantic models per design §8"
```

---

## Task 6: models/envelope.py — Envelope 主体 + builders

**Files:**
- Modify: `src/zotero_cli/models/envelope.py`
- Modify: `tests/unit/test_envelope.py`

`Envelope` 强制 `ok=True ⇒ error=None` 和 `ok=False ⇒ data=None`，避免 agent 拿到 inconsistent 状态。`success()` / `failure()` 是常用构造器。

- [ ] **Step 1: 追加测试**

```python
from zotero_cli.models.errors import ItemNotFoundError
from zotero_cli.models.envelope import Envelope


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
        # exit_code 进 meta 便于 agent 在不读 envelope 之外的进程退出码时也能拿到
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
```

- [ ] **Step 2: 追加实现到 `src/zotero_cli/models/envelope.py`**

```python
from pydantic import model_validator
from zotero_cli.models.errors import CLIError


class Envelope(BaseModel):
    """Top-level JSON envelope. ok flag governs which of data/error is populated."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Any = None
    error: ErrorObject | None = None
    meta: MetaObject

    @model_validator(mode="after")
    def _consistency(self) -> "Envelope":
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
    ) -> "Envelope":
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
    ) -> "Envelope":
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
```

- [ ] **Step 3: 跑测试 + commit**

```bash
uv run pytest tests/unit/test_envelope.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/models/envelope.py tests/unit/test_envelope.py
git commit -m "feat(envelope): add Envelope with success/failure builders and consistency validator"
```

---

## Task 7: utils/output.py — render 路由 + kv 格式

**Files:**
- Create: `src/zotero_cli/utils/output.py`
- Test: `tests/unit/test_output.py`

`render()` 是顶层入口。它接收 `(data, command, mode, all_fields, profile_filter, json_mode, quiet)`，按设计 §7.2 表选格式。本任务只实现路由 + `kv` 格式（单对象）。

**模式枚举**（`OutputMode`）：

| mode | 用途 | 例子命令 |
|---|---|---|
| `kv` | 单对象 | `items show` |
| `kv-list` | 对象列表 | `items list / search`、`feeds items`、`tags list` |
| `tree` | 层级 | `collections list` |
| `summary` | 写操作 | `items create / update / delete / attach` |
| `yaml` | 配置 | `config show` |
| `json` | 自省 | `schema` |

调用方传入 mode；`render()` 根据 `(json_mode, quiet, mode)` 决定最终输出格式。

- [ ] **Step 1: 写失败测试**

`tests/unit/test_output.py`：

```python
from __future__ import annotations

import json

import pytest

from zotero_cli.models.envelope import Envelope
from zotero_cli.utils.output import OutputMode, render


class TestRouter:
    def test_json_mode_always_returns_envelope_json(self) -> None:
        env = Envelope.success(
            data={"key": "ABC", "title": "T"},
            command="items.show",
            elapsed_ms=10,
        )
        out = render(envelope=env, mode=OutputMode.KV, json_mode=True, quiet=False)
        parsed = json.loads(out)
        assert parsed["ok"] is True
        assert parsed["data"] == {"key": "ABC", "title": "T"}

    def test_quiet_and_json_mutually_exclusive(self) -> None:
        from zotero_cli.models.errors import MutuallyExclusiveArgsError
        env = Envelope.success(data={}, command="x.y", elapsed_ms=1)
        with pytest.raises(MutuallyExclusiveArgsError):
            render(envelope=env, mode=OutputMode.KV, json_mode=True, quiet=True)


class TestKvFormat:
    def test_simple_dict(self) -> None:
        env = Envelope.success(
            data={"key": "ABC123XY", "title": "Attention is All You Need",
                  "itemType": "journalArticle"},
            command="items.show",
            elapsed_ms=10,
        )
        out = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        assert out == (
            "key: ABC123XY\n"
            "title: Attention is All You Need\n"
            "itemType: journalArticle\n"
        )

    def test_list_value_joined_with_semicolons(self) -> None:
        env = Envelope.success(
            data={"key": "X", "tags": ["transformer", "nlp"]},
            command="items.show",
            elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        assert "tags: transformer; nlp\n" in out

    def test_failure_kv_writes_error_to_returned_string_with_marker(self) -> None:
        from zotero_cli.models.errors import ItemNotFoundError
        env = Envelope.failure(
            ItemNotFoundError("Item ABC not found", hint="try items list"),
            command="items.show",
            elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False)
        # Default-mode 错误格式见设计 §9.3
        assert "✗ Error: ITEM_NOT_FOUND" in out
        assert "Item ABC not found" in out
        assert "Hint: try items list" in out


class TestFieldFilter:
    def test_kv_filter_restricts_fields(self) -> None:
        env = Envelope.success(
            data={"key": "ABC", "title": "T", "itemType": "art", "extra": "drop"},
            command="items.show", elapsed_ms=1,
        )
        out = render(
            envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False,
            field_filter=["key", "title"],
        )
        assert "key: ABC" in out
        assert "title: T" in out
        assert "itemType" not in out
        assert "extra" not in out

    def test_kv_filter_preserves_data_order(self) -> None:
        env = Envelope.success(
            data={"title": "T", "key": "ABC", "itemType": "art"},  # key 不在第一位
            command="items.show", elapsed_ms=1,
        )
        out = render(
            envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False,
            field_filter=["key", "title"],
        )
        # 输出按 data 中出现顺序，不按 field_filter 顺序
        assert out.index("title: T") < out.index("key: ABC")

    def test_field_filter_ignored_in_json_mode(self) -> None:
        env = Envelope.success(
            data={"key": "ABC", "title": "T", "extra": "kept"},
            command="items.show", elapsed_ms=1,
        )
        out = render(
            envelope=env, mode=OutputMode.KV, json_mode=True, quiet=False,
            field_filter=["key"],
        )
        assert '"extra": "kept"' in out  # JSON 模式忽略 field_filter

    def test_field_filter_none_returns_all_fields(self) -> None:
        env = Envelope.success(
            data={"key": "ABC", "title": "T"}, command="items.show", elapsed_ms=1,
        )
        out = render(
            envelope=env, mode=OutputMode.KV, json_mode=False, quiet=False,
            field_filter=None,
        )
        assert "title: T" in out
```

- [ ] **Step 2: 写实现**

`src/zotero_cli/utils/output.py`：

```python
"""Output rendering router (design §7).

render() is the single entry point. Stdout/stderr split (design §7.5):
render() returns the stdout string. Default-mode error rendering goes through
this function but the caller writes it to sys.stderr (since stdout stays empty
on errors in default mode).
"""
from __future__ import annotations

import enum
from typing import Any

from zotero_cli.models.envelope import Envelope
from zotero_cli.models.errors import MutuallyExclusiveArgsError


class OutputMode(enum.Enum):
    KV = "kv"
    KV_LIST = "kv-list"
    TREE = "tree"
    SUMMARY = "summary"
    YAML = "yaml"
    JSON = "json"


def render(
    *,
    envelope: Envelope,
    mode: OutputMode,
    json_mode: bool,
    quiet: bool,
    field_filter: list[str] | None = None,
) -> str:
    """Render an envelope to a stdout string.

    field_filter (design §7.4):
      - Only applied when not json_mode and not quiet.
      - For kv mode (single dict): restrict keys to those in field_filter (preserving
        original order in data, dropping unknown keys silently).
      - For kv-list mode (list of dicts): same restriction applied to each item.
      - tree / summary / yaml ignore field_filter (those formats have their own structure).
      - None or [] means "show all fields". --json mode always returns full fields.
    """
    if json_mode and quiet:
        raise MutuallyExclusiveArgsError(
            "--json and --quiet cannot be combined",
            hint="Use --json for full envelope, --quiet for affected_keys only.",
        )

    if json_mode:
        return envelope.model_dump_json(indent=2) + "\n"

    if not envelope.ok:
        return _render_default_error(envelope)

    if quiet:
        return _render_quiet(envelope)

    data = envelope.data
    if field_filter and mode in (OutputMode.KV, OutputMode.KV_LIST):
        data = _apply_field_filter(data, field_filter)

    if mode is OutputMode.KV:
        return _render_kv(data)

    raise NotImplementedError(f"render mode {mode.value} not yet implemented")


def _apply_field_filter(data: Any, fields: list[str]) -> Any:
    """Restrict dict keys to those in fields (preserving the order they appear in data)."""
    fields_set = set(fields)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields_set}
    if isinstance(data, list):
        return [
            {k: v for k, v in item.items() if k in fields_set} if isinstance(item, dict) else item
            for item in data
        ]
    return data



def _render_default_error(envelope: Envelope) -> str:
    err = envelope.error
    assert err is not None
    out = f"✗ Error: {err.code}\n  {err.message}\n"
    if err.hint:
        out += f"\n  Hint: {err.hint}\n"
    return out


def _render_quiet(envelope: Envelope) -> str:
    raise NotImplementedError("--quiet rendering deferred to Task 10")


def _render_kv(data: Any) -> str:
    if not isinstance(data, dict):
        raise ValueError(f"kv format requires dict, got {type(data).__name__}")
    return "\n".join(f"{k}: {_format_value(v)}" for k, v in data.items()) + "\n"


def _format_value(v: Any) -> str:
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    if v is None:
        return ""
    return str(v)
```

- [ ] **Step 3: 跑测试 + commit**

```bash
uv run pytest tests/unit/test_output.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/utils/output.py tests/unit/test_output.py
git commit -m "feat(output): add render router with kv format and json mode"
```

---

## Task 8: utils/output.py — kv-list + tree

**Files:** Modify `src/zotero_cli/utils/output.py` 和 `tests/unit/test_output.py`

`kv-list`：list[dict] → kv 块 + 空行分隔（设计 §7.3）。`tree`：含 `children` 的层级 dict → unicode tree。

- [ ] **Step 1: 测试**

```python
class TestKvList:
    def test_two_items_separated_by_blank_line(self) -> None:
        env = Envelope.success(
            data=[
                {"key": "ABC", "title": "First"},
                {"key": "DEF", "title": "Second"},
            ],
            command="items.list",
            elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.KV_LIST, json_mode=False, quiet=False)
        assert out == (
            "key: ABC\ntitle: First\n\n"
            "key: DEF\ntitle: Second\n"
        )

    def test_empty_list_returns_empty_string(self) -> None:
        env = Envelope.success(data=[], command="items.list", elapsed_ms=1)
        out = render(envelope=env, mode=OutputMode.KV_LIST, json_mode=False, quiet=False)
        assert out == ""


class TestTree:
    def test_simple_tree(self) -> None:
        env = Envelope.success(
            data={
                "name": "PhD Papers",
                "key": "COLL123",
                "items_count": 45,
                "children": [
                    {"name": "2024 Reading", "key": "COLL456", "items_count": 12,
                     "children": [
                         {"name": "Transformers", "key": "COLL789", "items_count": 8,
                          "children": []},
                     ]},
                    {"name": "Archive", "key": "COLL234", "items_count": 33, "children": []},
                ],
            },
            command="collections.list",
            elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.TREE, json_mode=False, quiet=False)
        assert "PhD Papers [COLL123] (45 items)" in out
        assert "├── 2024 Reading [COLL456] (12 items)" in out
        assert "│   └── Transformers [COLL789] (8 items)" in out
        assert "└── Archive [COLL234] (33 items)" in out
```

- [ ] **Step 2: 实现 — 在 `output.py` 路由内增加 KV_LIST / TREE 分支并加私有函数**

```python
# 在 render() 的 mode 分支中加（注意：使用 filter 后的 `data`，不是 envelope.data）：
if mode is OutputMode.KV_LIST:
    return _render_kv_list(data)
if mode is OutputMode.TREE:
    return _render_tree(envelope.data)  # tree 不参与 field_filter（设计 §7.4）

# 文件末尾加：
def _render_kv_list(data: Any) -> str:
    if not isinstance(data, list):
        raise ValueError(f"kv-list requires list, got {type(data).__name__}")
    if not data:
        return ""
    blocks = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"kv-list items must be dicts, got {type(item).__name__}")
        blocks.append("\n".join(f"{k}: {_format_value(v)}" for k, v in item.items()))
    return "\n\n".join(blocks) + "\n"


def _render_tree(data: Any) -> str:
    if not isinstance(data, dict):
        raise ValueError(f"tree requires dict, got {type(data).__name__}")
    lines: list[str] = []
    _walk_tree(data, prefix="", is_last=True, is_root=True, out=lines)
    return "\n".join(lines) + "\n"


def _walk_tree(
    node: dict[str, Any],
    *,
    prefix: str,
    is_last: bool,
    is_root: bool,
    out: list[str],
) -> None:
    label = f"{node['name']} [{node['key']}] ({node['items_count']} items)"
    if is_root:
        out.append(label)
        new_prefix = ""
    else:
        connector = "└── " if is_last else "├── "
        out.append(prefix + connector + label)
        new_prefix = prefix + ("    " if is_last else "│   ")
    children = node.get("children") or []
    for i, child in enumerate(children):
        _walk_tree(
            child,
            prefix=new_prefix,
            is_last=(i == len(children) - 1),
            is_root=False,
            out=out,
        )
```

- [ ] **Step 3: 跑测试 + commit**

```bash
uv run pytest tests/unit/test_output.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/utils/output.py tests/unit/test_output.py
git commit -m "feat(output): add kv-list and tree renderers"
```

---

## Task 9: utils/output.py — summary + yaml（含密钥掩码）

**Files:** Modify `output.py` 和 `test_output.py`

`summary`：写操作结果（设计 §7.3 格式）。`yaml`：配置展示（`config show`），敏感字段（api_key、password）掩码。

- [ ] **Step 1: 测试**

```python
class TestSummary:
    def test_create_success(self) -> None:
        env = Envelope.success(
            data={
                "successful": [
                    {"index": 0, "key": "ABC", "version": 5679},
                    {"index": 1, "key": "DEF", "version": 5680},
                ],
                "unchanged": [],
                "failed": [],
            },
            command="items.create",
            elapsed_ms=10,
            meta_extra={"affected_keys": ["ABC", "DEF"]},
        )
        out = render(envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False)
        assert "✓ Created 2 items:" in out
        assert "ABC, DEF" in out

    def test_with_failures(self) -> None:
        env = Envelope.success(
            data={
                "successful": [{"index": 0, "key": "ABC", "version": 1}],
                "unchanged": [],
                "failed": [
                    {"index": 1, "code": "INVALID_ITEM_TYPE",
                     "message": "Invalid item type: foo",
                     "context": {"itemType": "foo"}},
                ],
            },
            command="items.create",
            elapsed_ms=10,
            meta_extra={"affected_keys": ["ABC"]},
        )
        out = render(envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=False)
        assert "✓ Created 1 item:" in out
        assert "ABC" in out
        assert "✗ 1 item failed:" in out
        assert "INVALID_ITEM_TYPE" in out


class TestYaml:
    def test_masks_api_key(self) -> None:
        env = Envelope.success(
            data={"profile": "default", "api_key": "abcd1234efgh5678",
                  "library_id": "12345"},
            command="config.show", elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.YAML, json_mode=False, quiet=False)
        assert "abcd****" in out
        assert "abcd1234efgh5678" not in out
        assert "library_id: '12345'" in out or "library_id: 12345" in out

    def test_masks_password_in_nested_webdav(self) -> None:
        env = Envelope.success(
            data={
                "profile": "default",
                "webdav": {"url": "https://x", "username": "u", "password": "secret123"},
            },
            command="config.show", elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.YAML, json_mode=False, quiet=False)
        assert "secret123" not in out
        assert "password: '****'" in out or "password: ****" in out

    def test_quiet_unsupported_for_yaml(self) -> None:
        from zotero_cli.models.errors import MutuallyExclusiveArgsError
        env = Envelope.success(data={}, command="config.show", elapsed_ms=1)
        with pytest.raises(MutuallyExclusiveArgsError):
            render(envelope=env, mode=OutputMode.YAML, json_mode=False, quiet=True)
```

- [ ] **Step 2: 实现 — 加 SUMMARY / YAML 分支与函数**

```python
# 顶部加：
import yaml as _yaml

_SENSITIVE_KEYS = {"password", "api_key"}


# render() 内 quiet 分支前加：
if quiet and mode is OutputMode.YAML:
    raise MutuallyExclusiveArgsError(
        "--quiet is not supported for config display",
        hint="Use --json for machine-readable output.",
    )


# render() 的 mode 分支加：
if mode is OutputMode.SUMMARY:
    return _render_summary(envelope)
if mode is OutputMode.YAML:
    return _render_yaml(envelope.data)


# 文件末尾加：
def _render_summary(envelope: Envelope) -> str:
    data = envelope.data
    cmd = envelope.meta.command
    verb = {
        "items.create": "Created", "items.update": "Updated",
        "items.delete": "Deleted", "items.attach": "Attached",
        "collections.create": "Created", "collections.update": "Updated",
        "collections.delete": "Deleted", "tags.add": "Tagged",
        "tags.remove": "Untagged", "tags.delete": "Deleted",
        "tags.rename": "Renamed",
    }.get(cmd, "Affected")

    successful = data.get("successful", [])
    failed = data.get("failed", [])
    out = ""
    if successful:
        keys = ", ".join(s["key"] for s in successful)
        plural = "items" if len(successful) != 1 else "item"
        out += f"✓ {verb} {len(successful)} {plural}:\n  {keys}\n"
    if failed:
        if out:
            out += "\n"
        plural = "items" if len(failed) != 1 else "item"
        out += f"✗ {len(failed)} {plural} failed:\n"
        for f in failed:
            out += f"  {f.get('code', 'ERROR')}: {f['message']}\n"
    return out or "(nothing changed)\n"


def _mask_value(value: Any, key: str) -> Any:
    if key not in _SENSITIVE_KEYS or value is None:
        return value
    s = str(value)
    if key == "api_key" and len(s) >= 4:
        return f"{s[:4]}****"
    return "****"


def _mask_recursive(obj: Any, parent_key: str = "") -> Any:
    if isinstance(obj, dict):
        return {k: _mask_recursive(_mask_value(v, k), k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_recursive(x, parent_key) for x in obj]
    return obj


def _render_yaml(data: Any) -> str:
    masked = _mask_recursive(data)
    return _yaml.safe_dump(masked, sort_keys=False, default_flow_style=False)
```

- [ ] **Step 3: 跑测试 + commit**

```bash
uv run pytest tests/unit/test_output.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/utils/output.py tests/unit/test_output.py
git commit -m "feat(output): add summary and yaml renderers with sensitive masking"
```

---

## Task 10: utils/output.py — --quiet 渲染

**Files:** Modify `output.py` 和 `test_output.py`

`--quiet` 行为（设计 §7.2 / §7.2.1）：

- 列表（kv-list、tree）：每行一个 key（取 data 各项的 `key` 字段）
- 单对象（kv）：仅一行 key
- 写操作（summary）：`meta.affected_keys` 每行一个；空时**完全无输出**（0 字节）
- 附件（summary，含 backend）：同写操作，输出 `meta.affected_keys`
- yaml / json 模式：拒绝（已在 Task 9 实现）

- [ ] **Step 1: 测试**

```python
class TestQuiet:
    def test_kv_list_outputs_keys_one_per_line(self) -> None:
        env = Envelope.success(
            data=[{"key": "ABC", "title": "T1"}, {"key": "DEF", "title": "T2"}],
            command="items.list", elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.KV_LIST, json_mode=False, quiet=True)
        assert out == "ABC\nDEF\n"

    def test_kv_single_outputs_one_key(self) -> None:
        env = Envelope.success(
            data={"key": "ABC", "title": "T"},
            command="items.show", elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.KV, json_mode=False, quiet=True)
        assert out == "ABC\n"

    def test_summary_uses_affected_keys(self) -> None:
        env = Envelope.success(
            data={"successful": [{"key": "ABC"}, {"key": "DEF"}],
                  "unchanged": [], "failed": []},
            command="items.create", elapsed_ms=1,
            meta_extra={"affected_keys": ["ABC", "DEF"]},
        )
        out = render(envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=True)
        assert out == "ABC\nDEF\n"

    def test_summary_empty_affected_keys_outputs_zero_bytes(self) -> None:
        # 设计 §7.2.1：affected_keys 为空时 stdout 完全为空（0 字节、0 行）
        env = Envelope.success(
            data={"successful": [], "unchanged": [{"key": "X"}], "failed": []},
            command="items.attach", elapsed_ms=1,
            meta_extra={"affected_keys": []},
        )
        out = render(envelope=env, mode=OutputMode.SUMMARY, json_mode=False, quiet=True)
        assert out == ""

    def test_tree_outputs_root_and_children_keys(self) -> None:
        env = Envelope.success(
            data={"name": "Root", "key": "R", "items_count": 0,
                  "children": [{"name": "C", "key": "C1", "items_count": 0,
                                "children": []}]},
            command="collections.list", elapsed_ms=1,
        )
        out = render(envelope=env, mode=OutputMode.TREE, json_mode=False, quiet=True)
        assert out == "R\nC1\n"
```

- [ ] **Step 2: 实现 — 替换 `_render_quiet` 占位**

```python
def _render_quiet(envelope: Envelope) -> str:
    cmd = envelope.meta.command
    is_write_op = any(
        cmd.startswith(p) for p in
        ("items.create", "items.update", "items.delete", "items.attach",
         "collections.create", "collections.update", "collections.delete",
         "tags.add", "tags.remove", "tags.rename", "tags.delete")
    )
    if is_write_op:
        keys = envelope.meta.model_dump().get("affected_keys", [])
        return ("\n".join(keys) + "\n") if keys else ""

    data = envelope.data
    if isinstance(data, list):
        return ("\n".join(item["key"] for item in data) + "\n") if data else ""
    if isinstance(data, dict):
        if "children" in data:
            keys: list[str] = []
            _collect_tree_keys(data, keys)
            return "\n".join(keys) + "\n"
        return data["key"] + "\n"
    raise ValueError(f"--quiet not applicable to data type {type(data).__name__}")


def _collect_tree_keys(node: dict[str, Any], out: list[str]) -> None:
    out.append(node["key"])
    for child in node.get("children") or []:
        _collect_tree_keys(child, out)
```

- [ ] **Step 3: 跑测试 + commit**

```bash
uv run pytest tests/unit/test_output.py -v
uv run ruff check src tests && uv run mypy src
git add src/zotero_cli/utils/output.py tests/unit/test_output.py
git commit -m "feat(output): implement --quiet rendering for all modes"
```

---

## Task 11: utils/audit_log.py — 基础 JSONL 写入

**Files:** `src/zotero_cli/utils/audit_log.py`、`tests/unit/test_audit_log.py`

设计 §9.4：JSONL 文件，每行一个 entry。本任务只做基础写入。

**关键测试**（写到 `tests/unit/test_audit_log.py`）：

```python
from __future__ import annotations
import json
from pathlib import Path
import pytest
from zotero_cli.utils.audit_log import AuditEntry, write_entry


def test_writes_jsonl_line(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    entry = AuditEntry(
        timestamp="2026-06-07T14:23:45Z", profile="default",
        command="items.create", args={"title": "Paper"},
        result="success", affected_keys=["ABC"], elapsed_ms=234,
    )
    write_entry(log_path=log, entry=entry)
    parsed = json.loads(log.read_text().splitlines()[0])
    assert parsed["command"] == "items.create"
    assert parsed["affected_keys"] == ["ABC"]


def test_appends_multiple_entries(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    for i in range(3):
        write_entry(log_path=log, entry=AuditEntry(
            timestamp="t", profile="p", command=f"x.y.{i}", args={},
            result="success", affected_keys=[], elapsed_ms=1,
        ))
    assert len(log.read_text().splitlines()) == 3


def test_creates_parent_dir(tmp_path: Path) -> None:
    log = tmp_path / "sub" / "audit.log"
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="x.y", args={},
        result="success", affected_keys=[], elapsed_ms=0,
    ))
    assert log.exists()


def test_failure_includes_error_fields(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="items.create", args={},
        result="failure", affected_keys=[], elapsed_ms=10,
        error_code="API_TIMEOUT", error_message="timed out",
    ))
    parsed = json.loads(log.read_text().splitlines()[0])
    assert parsed["result"] == "failure"
    assert parsed["error_code"] == "API_TIMEOUT"
```

**实现**（`src/zotero_cli/utils/audit_log.py`）：

```python
"""JSONL audit log per design §9.4. Captures only write operations."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from zotero_cli.constants import AUDIT_LOG_ROTATE_BYTES  # 用于 Task 13


@dataclass
class AuditEntry:
    timestamp: str
    profile: str
    command: str
    args: dict
    result: str
    affected_keys: list[str]
    elapsed_ms: int
    error_code: str | None = None
    error_message: str | None = None


def write_entry(*, log_path: Path, entry: AuditEntry) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw = asdict(entry)
    payload = {k: v for k, v in raw.items()
               if v is not None or k in {"args", "affected_keys"}}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
```

**Steps**：
- [ ] 写测试
- [ ] 跑测试确认失败
- [ ] 写实现
- [ ] 跑测试确认通过
- [ ] `uv run ruff check && uv run mypy src`
- [ ] commit `feat(audit_log): basic JSONL append writer`

---

## Task 12: utils/audit_log.py — 敏感字段掩码

**Files:** Modify `audit_log.py` 和 `test_audit_log.py`

设计 §9.4 / DEVELOPMENT.md §10.2：API key 前 4 位 + `****`；password 完全 redact；嵌套字段递归处理。

**关键测试**：

```python
def test_api_key_field_masked(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="config.set",
        args={"key": "api_key", "value": "abcd1234efgh5678"},
        result="success", affected_keys=[], elapsed_ms=1,
    ))
    parsed = json.loads(log.read_text().splitlines()[0])
    assert parsed["args"]["value"] == "abcd****"


def test_password_redacted(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="config.set",
        args={"key": "password", "value": "secret123"},
        result="success", affected_keys=[], elapsed_ms=1,
    ))
    text = log.read_text()
    assert "secret123" not in text


def test_nested_password_redacted(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="config.set",
        args={"webdav": {"url": "https://x", "password": "s3cret"}},
        result="success", affected_keys=[], elapsed_ms=1,
    ))
    assert "s3cret" not in log.read_text()


def test_short_api_key_fully_masked(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="config.set",
        args={"key": "api_key", "value": "abc"},
        result="success", affected_keys=[], elapsed_ms=1,
    ))
    parsed = json.loads(log.read_text().splitlines()[0])
    assert parsed["args"]["value"] == "****"
```

**实现**（修改 `audit_log.py`）：

```python
_API_KEY_NAMES = {"api_key", "api-key", "apiKey"}
_REDACT_NAMES = {"password"}


def _mask_args(obj):
    if isinstance(obj, dict):
        result = {}
        # config.set style: {"key": "<name>", "value": "<value>"}
        if obj.get("key") in _API_KEY_NAMES and "value" in obj:
            v = obj["value"]
            result = dict(obj)
            result["value"] = f"{v[:4]}****" if isinstance(v, str) and len(v) >= 4 else "****"
            return result
        if obj.get("key") in _REDACT_NAMES and "value" in obj:
            result = dict(obj)
            result["value"] = "[REDACTED]"
            return result
        for k, v in obj.items():
            if k in _REDACT_NAMES:
                result[k] = "[REDACTED]"
            elif k in _API_KEY_NAMES and isinstance(v, str):
                result[k] = f"{v[:4]}****" if len(v) >= 4 else "****"
            else:
                result[k] = _mask_args(v)
        return result
    if isinstance(obj, list):
        return [_mask_args(x) for x in obj]
    return obj


def write_entry(*, log_path: Path, entry: AuditEntry) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw = asdict(entry)
    raw["args"] = _mask_args(raw["args"])
    payload = {k: v for k, v in raw.items()
               if v is not None or k in {"args", "affected_keys"}}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
```

**Steps**：写测试 → 失败 → 加 `_mask_args` → 通过 → ruff + mypy → commit `feat(audit_log): mask api_key and redact password before writing`

---

## Task 13: utils/audit_log.py — 10MB 自动轮转

**Files:** Modify `audit_log.py` 和 `test_audit_log.py`

设计 §9.4：单文件 ≥10MB 自动 gzip 归档为 `audit.log.YYYY-MM.gz`，原文件清空后写新 entry。

**关键测试**：

```python
import gzip


def test_no_rotation_below_threshold(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    log.write_text("x\n" * 100)
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="t", profile="p", command="x.y", args={},
        result="success", affected_keys=[], elapsed_ms=0,
    ))
    assert not list(tmp_path.glob("audit.log.*"))


def test_rotates_at_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zotero_cli.utils import audit_log
    monkeypatch.setattr(audit_log, "AUDIT_LOG_ROTATE_BYTES", 100)

    log = tmp_path / "audit.log"
    log.write_text("OLD CONTENT " * 20)
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="2026-06-07T14:23:45Z", profile="p", command="x.y", args={},
        result="success", affected_keys=[], elapsed_ms=0,
    ))
    archives = list(tmp_path.glob("audit.log.*.gz"))
    assert len(archives) == 1
    assert archives[0].name.startswith("audit.log.2026-06")
    with gzip.open(archives[0], "rt") as f:
        assert "OLD CONTENT" in f.read()
    # 新文件只含一行新 entry
    assert log.read_text().count("\n") == 1


def test_archive_name_uses_entry_year_month(tmp_path: Path, monkeypatch) -> None:
    from zotero_cli.utils import audit_log
    monkeypatch.setattr(audit_log, "AUDIT_LOG_ROTATE_BYTES", 100)

    log = tmp_path / "audit.log"
    log.write_text("x" * 200)
    write_entry(log_path=log, entry=AuditEntry(
        timestamp="2026-12-15T00:00:00Z", profile="p", command="x.y", args={},
        result="success", affected_keys=[], elapsed_ms=0,
    ))
    assert (tmp_path / "audit.log.2026-12.gz").exists()
```

**实现**（在 `write_entry` 写文件前先检查大小、按需轮转）：

```python
import gzip
import shutil


def _maybe_rotate(log_path: Path, entry_timestamp: str) -> None:
    if not log_path.exists():
        return
    if log_path.stat().st_size < AUDIT_LOG_ROTATE_BYTES:
        return
    # 取 entry timestamp 的 YYYY-MM
    year_month = entry_timestamp[:7]  # "2026-06-07T..." → "2026-06"
    archive = log_path.with_name(f"{log_path.name}.{year_month}.gz")
    # 若同月归档已存在，追加（先解压、合并、再压缩）；否则直接压缩
    if archive.exists():
        # 简单策略：用增量后缀避免重复
        i = 1
        while archive.with_suffix(f".gz.{i}").exists():
            i += 1
        archive = archive.with_suffix(f".gz.{i}")
    with log_path.open("rb") as src, gzip.open(archive, "wb") as dst:
        shutil.copyfileobj(src, dst)
    log_path.write_text("")  # truncate


def write_entry(*, log_path: Path, entry: AuditEntry) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _maybe_rotate(log_path, entry.timestamp)
    raw = asdict(entry)
    raw["args"] = _mask_args(raw["args"])
    payload = {k: v for k, v in raw.items()
               if v is not None or k in {"args", "affected_keys"}}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
```

**Steps**：写测试 → 失败 → 加 `_maybe_rotate` 调用 → 通过 → ruff + mypy → commit `feat(audit_log): add 10MB gzip rotation per design §9.4`

---

## Task 14: utils/date_parser.py — 正则 + `_validate_month`

**Files:** `src/zotero_cli/utils/date_parser.py`、`tests/unit/test_date_parser.py`

设计 §11.4 已给出完整代码（lines 1119-1190）。本任务只引入正则常量 + `_validate_month` 辅助 + 数据类。

**关键测试**：

```python
import re
from datetime import datetime
import pytest

from zotero_cli.utils.date_parser import (
    YEAR_RE, YEAR_MONTH_RE, ISO_DATE_RE, _validate_month, DateRange,
)
from zotero_cli.models.errors import InvalidDateFormatError


@pytest.mark.parametrize("s", ["2024", "1900", "9999"])
def test_year_re_matches(s: str) -> None:
    assert YEAR_RE.match(s)


@pytest.mark.parametrize("s", ["24", "20240", "2024a", "2024-"])
def test_year_re_rejects(s: str) -> None:
    assert not YEAR_RE.match(s)


@pytest.mark.parametrize("s", ["2024-01", "2024-12"])
def test_year_month_re_matches(s: str) -> None:
    assert YEAR_MONTH_RE.match(s)


@pytest.mark.parametrize("s", ["2024-1", "2024/01", "2024-13"])
def test_year_month_re_rejects(s: str) -> None:
    # 注意 "2024-13" 通过正则但要靠 _validate_month 拦截
    if s == "2024-13":
        with pytest.raises(InvalidDateFormatError):
            _validate_month(2024, 13)
    else:
        assert not YEAR_MONTH_RE.match(s)


@pytest.mark.parametrize("month", [1, 6, 12])
def test_validate_month_accepts_valid(month: int) -> None:
    _validate_month(2024, month)  # no raise


@pytest.mark.parametrize("month", [0, 13, -1, 100])
def test_validate_month_rejects_invalid(month: int) -> None:
    with pytest.raises(InvalidDateFormatError):
        _validate_month(2024, month)


def test_date_range_dataclass() -> None:
    r = DateRange("2024-01-01", "2024-12-31")
    assert r.start == "2024-01-01"
    assert r.end == "2024-12-31"
```

**实现**：参考设计 §11.4（lines 1119-1190），先抽取常量与辅助：

```python
"""Date range parser per design §11.4. SQL-end string bounds for filtering
multipart date values stored in itemDataValues.value (design §11.2)."""
from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime

from zotero_cli.models.errors import InvalidDateFormatError

YEAR_RE = re.compile(r"^\d{4}$")
YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class DateRange:
    start: str
    end: str


def _validate_month(year: int, month: int) -> None:
    if not (1 <= month <= 12):
        raise InvalidDateFormatError(
            f"Invalid month '{month:02d}' in date input",
            hint="Month must be 01-12",
        )
```

**Steps**：写测试 → 失败 → 加常量 + dataclass + `_validate_month` → 通过 → commit `feat(date_parser): add regex patterns and month validator`

---

## Task 15: utils/date_parser.py — `_to_start_bound` + `_to_end_bound`

**Files:** Modify `date_parser.py` 和 `test_date_parser.py`

实现两个辅助函数，按设计 §11.4 转换表：

| 输入 | start | end |
|---|---|---|
| `2024-06-15` | `2024-06-15` | `2024-06-15` |
| `2024-06` | `2024-06-00` | `2024-06-30` |
| `2024` | `2024-00-00` | `2024-12-31` |

**关键测试**：

```python
from zotero_cli.utils.date_parser import _to_start_bound, _to_end_bound


@pytest.mark.parametrize("inp,expected_start,expected_end", [
    ("2024", "2024-00-00", "2024-12-31"),
    ("2024-06", "2024-06-00", "2024-06-30"),
    ("2024-02", "2024-02-00", "2024-02-29"),  # 闰年
    ("2023-02", "2023-02-00", "2023-02-28"),
    ("2024-06-15", "2024-06-15", "2024-06-15"),
    ("2024-12-31", "2024-12-31", "2024-12-31"),
])
def test_bounds(inp: str, expected_start: str, expected_end: str) -> None:
    assert _to_start_bound(inp) == expected_start
    assert _to_end_bound(inp) == expected_end


@pytest.mark.parametrize("bad", [
    "June 24", "2024/06", "24-06", "2024-13", "2024-1", "2024-02-30", "2023-02-29",
])
def test_bounds_invalid_input_raises(bad: str) -> None:
    with pytest.raises(InvalidDateFormatError):
        _to_start_bound(bad)
    with pytest.raises(InvalidDateFormatError):
        _to_end_bound(bad)
```

**实现**：照抄设计 §11.4 的 `_to_start_bound` 和 `_to_end_bound`（lines 1151-1189）。

**Steps**：写测试 → 失败 → 实现 → 通过 → commit `feat(date_parser): add _to_start_bound and _to_end_bound per design §11.4`

---

## Task 16: utils/date_parser.py — `date_range_to_sql_bounds`（单值 + 范围）

**Files:** Modify `date_parser.py` 和 `test_date_parser.py`

合并单值 / 范围 / 开区间 解析。设计 §11.4 转换表：

| 输入 | start | end |
|---|---|---|
| `2024` | `2024-00-00` | `2024-12-31` |
| `2024-06-15` | `2024-06-15` | `2024-06-15` |
| `2024-01..2024-06` | `2024-01-00` | `2024-06-30` |
| `2024-06-15..` | `2024-06-15` | `9999-12-31` |
| `..2024-06-15` | `0000-00-00` | `2024-06-15` |

**关键测试**：

```python
from zotero_cli.utils.date_parser import date_range_to_sql_bounds


@pytest.mark.parametrize("inp,expected", [
    ("2024", DateRange("2024-00-00", "2024-12-31")),
    ("2024-06-15", DateRange("2024-06-15", "2024-06-15")),
    ("2024-01..2024-06", DateRange("2024-01-00", "2024-06-30")),
    ("2024-06-15..", DateRange("2024-06-15", "9999-12-31")),
    ("..2024-06-15", DateRange("0000-00-00", "2024-06-15")),
    ("..", DateRange("0000-00-00", "9999-12-31")),  # 空范围（含所有）
])
def test_date_range_to_sql_bounds(inp: str, expected: DateRange) -> None:
    assert date_range_to_sql_bounds(inp) == expected


def test_whitespace_stripped() -> None:
    assert date_range_to_sql_bounds("  2024  ") == DateRange("2024-00-00", "2024-12-31")


def test_range_with_spaces_around_dotdot() -> None:
    assert date_range_to_sql_bounds("2024-01 .. 2024-06") == DateRange(
        "2024-01-00", "2024-06-30"
    )
```

**实现**：照抄设计 §11.4 的 `date_range_to_sql_bounds`（lines 1128-1142）。

**Steps**：测试 → 失败 → 实现 → 通过 → commit `feat(date_parser): add date_range_to_sql_bounds public API`

---

## Task 17: utils/date_parser.py — 错误场景全覆盖

**Files:** Modify `test_date_parser.py`

补全所有错误路径的测试，确保设计 §11.4 列出的所有非法输入都按预期抛 `InvalidDateFormatError` 且 hint 准确。

**关键测试**：

```python
@pytest.mark.parametrize("inp", [
    "June 24", "2024/06", "24-06",
    "2024-13", "2024-00", "2024-1", "2024-002",
    "2024-02-30", "2023-02-29", "2024-04-31",
    "abc", "", "..2024..2025",  # 多个 ..
])
def test_invalid_inputs(inp: str) -> None:
    with pytest.raises(InvalidDateFormatError) as ei:
        date_range_to_sql_bounds(inp)
    # hint 必须存在且非空
    assert ei.value.hint


def test_hint_for_unrecognized_format() -> None:
    with pytest.raises(InvalidDateFormatError) as ei:
        date_range_to_sql_bounds("June 24")
    assert "YYYY" in (ei.value.hint or "")
```

**实现注意**：如果 `..` 出现多次（`partition` 已处理），但若设计要求"`..2024..2025` 应报错"，则在 `date_range_to_sql_bounds` 入口加 `if arg.count("..") > 1: raise InvalidDateFormatError(...)`。

**Steps**：补测试 → 跑测试 → 按需补实现 → 通过 → commit `test(date_parser): cover all invalid input cases per design §11.4`

---

## Task 18: 阶段 1 整体覆盖率验证 + DEVELOPMENT.md §9.1 勾选

**Files:** `DEVELOPMENT.md`（如更新）

- [ ] **Step 1: 跑完整自检**

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src/zotero_cli --cov-report=term-missing
```

- [ ] **Step 2: 验证覆盖率目标**

`pytest --cov` 输出中确认（设计 §12.4 / DEVELOPMENT.md §9.1）：

| 模块 | 目标 | 实测 |
|---|---|---|
| `utils/date_parser.py` | 100% | ____ |
| `utils/output.py` | 90%+ | ____ |
| `utils/audit_log.py` | 90%+ | ____ |
| `models/errors.py` | 95%+ | ____ |
| `models/envelope.py` | 95%+ | ____ |
| `utils/exit_codes.py` | 100% | ____ |

未达标 → 补测试 → 重跑。

- [ ] **Step 3: 勾选 DEVELOPMENT.md §9.1 checklist**

在 DEVELOPMENT.md §9.1 中把每条勾选状态从 `[ ]` 改为 `[x]`。

- [ ] **Step 4: commit**

```bash
git add DEVELOPMENT.md
git commit -m "docs: tick phase 1 acceptance checklist"
```

阶段 1 完成。下一步进入阶段 2（配置层），见 `2026-06-07-phase-2-config.md`。

---

## 自检清单（全阶段汇总）

每次 PR 之前：

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src/zotero_cli --cov-report=term-missing
```

四项全过才能 commit / merge。

---

## 阶段验收 checklist

参见 `DEVELOPMENT.md §9.1`。

---

## 阶段 1 接口契约（给下游阶段消费）

下游阶段（Phase 2-6）调 Phase 1 模块时遵守以下契约。**契约变化必须改本节并通告 Phase 2-6 同步。**

### A. `render()` 调用约定

```python
render(
    *,
    envelope: Envelope,
    mode: OutputMode,           # KV / KV_LIST / TREE / SUMMARY / YAML / JSON
    json_mode: bool,            # 全局 --json
    quiet: bool,                # 全局 --quiet（与 json_mode 互斥）
    field_filter: list[str] | None = None,  # 设计 §7.4
) -> str
```

- `field_filter`：仅 `KV` / `KV_LIST` 模式生效；`TREE` / `SUMMARY` / `YAML` 自带固定结构，忽略此参数；`JSON` 模式永远返回完整字段
- 命令层 ＝ "解析 `--all-fields` flag → 决定传 None（全字段）或传 config 中的字段列表"
- 字段不存在于 data 中时静默丢弃，不抛错

### B. list-data 项的 `key` 字段约定（quiet 模式依赖）

`render(quiet=True)` 在 `KV_LIST` / `KV` / `TREE` 模式下读取每个数据项的 `key` 字段。

**所有进入 envelope `data` 的 list 项目模型必须有 `key: str` 字段。** 各阶段对应：

| 模型 | `key` 取值 |
|---|---|
| `Item`（Phase 3）| Zotero `key`（如 `"ABC123XY"`），原生即有 |
| `Collection`（Phase 3）| Zotero `key`，原生即有 |
| `Tag`（Phase 3）| `tag` 字符串本身即作为 key |
| `FeedSummary`（Phase 5）| `str(feed_id)`（feed_id 是整数 libraryID） |
| `FeedItem`（Phase 5）| `str(item_id)` |

实现方式：pydantic `computed_field` 或显式赋值都可。tree 节点已要求有 `key`（见 Task 8）。

### C. envelope `meta.affected_keys`（写操作）

`--quiet` 模式下写操作命令的 stdout 严格 = `meta.affected_keys`，每行一个；`affected_keys` 为空 = stdout 0 字节。

设计 §7.2.1 / §8.3.1 详细规则：unchanged / failed 项**不进** `affected_keys`。

### D. 错误流向

`adapter` 层捕获外部库异常 → 翻译为 `models/errors.py` 的 CLIError 子类 → 透传到 `command` 层最外层 try/except → 调 `Envelope.failure(err, ...)` → `render(...)` → 写 stderr（默认模式）/ stdout（json 模式）。

详见 DEVELOPMENT.md §4.3 错误处理三层流。


















