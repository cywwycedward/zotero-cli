# 阶段 3：Zotero API 适配（pyzotero）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**：先做 pyzotero spike 锁定附件 API 实测行为（决定后续 mock 策略），然后实现 `adapters/zotero_api.py` 的非附件部分 + items/collections/tags/export 的 service 与 command 层（**不含 `items attach` / `--attach` flag，留给阶段 4**）。所有写操作接入 `audit_log.write_entry`，`--quiet` / `--json` 互斥在 command 层兜底。

**Architecture**：commands → services → adapters → pyzotero。adapter 层翻译 pyzotero 异常为 §10.0.2.6 错误码；service 层组装 envelope 结果；command 层用 Typer 声明参数 + 调 `utils.output.render`。

**Tech Stack**：pyzotero 1.5+ / pytest + respx（pending spike）/ pytest-mock fallback / Typer。

**Source-of-truth references**：
- 设计文档：`docs/superpowers/specs/2026-06-07-zotero-cli-design.md`（§6 命令树、§7 输出、§8 envelope、§9 错误、§10.0.2 ZFS、§13 阶段 3）
- 协作规范：`DEVELOPMENT.md`（§4.3 错误流向、§5 分层、§6 测试、§9.3 阶段 3 验收）
- 阶段 1 已落地：`models/errors.py`、`models/envelope.py`、`utils/output.py`、`utils/audit_log.py`、`utils/exit_codes.py`
- 阶段 2 已落地（假设）：`models/config.py`（`Config` / `ProfileConfig` / `WebDAVConfig`）、`services/config_service.py`（`load_config(profile) -> ProfileConfig`）

---

## 文件结构

```
src/zotero_cli/
├── adapters/
│   ├── __init__.py
│   └── zotero_api.py                # ZoteroAPI + _select_backend + 异常翻译
├── services/
│   ├── __init__.py
│   ├── item_service.py              # ItemService
│   ├── collection_service.py        # CollectionService
│   ├── tag_service.py               # TagService
│   └── export_service.py            # ExportService
└── commands/
    ├── __init__.py
    ├── items.py                     # list/search/show/create/update/delete/export
    ├── collections.py               # list/show/create/update/delete/add-items/remove-items
    └── tags.py                      # list/add/remove/rename/delete
tests/
├── unit/
│   ├── test_zotero_api.py
│   ├── test_item_service.py
│   ├── test_collection_service.py
│   ├── test_tag_service.py
│   ├── test_export_service.py
│   ├── test_affected_keys.py        # 参数化覆盖 §7.2.1 边界
│   └── test_command_mutex.py        # --quiet/--json 互斥在 command 层兜底
└── integration/
    ├── test_items_commands.py
    ├── test_collections_commands.py
    └── test_tags_commands.py
docs/superpowers/specs/spikes/
└── pyzotero-attachment-api.md       # Task 1 产物
```

---

## 模块依赖关系

```
adapters/zotero_api.py  (依赖 models/errors + models/config)
           ↓
services/item_service.py  ──┐
services/collection_service.py
services/tag_service.py
services/export_service.py  ──┘  (协调 adapter，组装 envelope-ready dict)
           ↓
commands/items.py
commands/collections.py
commands/tags.py            (Typer 入口；调 service + render + audit_log + sys.exit)
```

**任务执行顺序**：Task 1 (spike) → 2 → 3 → 4 (adapter 三件套) → 5 → 6 → 7 (item service) → 8 → 9 (item commands) → 10 (collections) → 11 (tags) → 12 (export) → 13 (affected_keys 参数化) → 14 (mutex 兜底) → 15 (验收勾选)。

Item service / commands 必须在 collection / tag / export 之前完成（其他 service 的测试会复用 ItemService 的 mock 模式）。

---

## Task 1: pyzotero spike — 实测附件 API 与 respx 覆盖性

**Files:**
- Create: `docs/superpowers/specs/spikes/pyzotero-attachment-api.md`

**Goal**：验证设计 §10.0.2.1 表四个 API（`attachment_simple` / `attachment_both` / `upload_attachments` / `Zupload`）的实际行为；验证 `upload_attachments(parentid=None, template['key']=existing)` 真能重传到已有 attachment；验证 `unchanged` 返回时 0 网络上传；验证 respx 能否拦截 pyzotero 的 httpx 请求（决定 §6.3 mock 栈）。

**约束**：用真实测试账号（个人 sandbox library），不污染主 library。所有原始抓包结果（HTTP method / URL / status / 关键 header / 响应 body 摘要）粘进文档。

- [ ] **Step 1**：在 `spike/pyzotero-attachment-api` 分支起一个简单脚本 `_spike.py`，覆盖以下场景，每个场景启用 `respx.mock(assert_all_called=False)` 包住调用，记录是否被拦截：
  1. `Zotero(...).attachment_simple(['/tmp/sample.pdf'], parentid=PARENT_KEY)` → 看 `success/failure/unchanged` 结构
  2. 同上文件第二次执行 → 期望进 `unchanged`，respx 应**完全无 PUT 请求**
  3. `Zotero(...).attachment_both([('My Title', '/tmp/sample.pdf')], parentid=PARENT_KEY)` → 看 title 是否生效
  4. `tpl = zot.item_template('attachment','imported_file'); tpl['key']=ATT_KEY; tpl['filename']='/tmp/sample.pdf'; zot.upload_attachments([tpl], parentid=None)` → 看是否真重传到 ATT_KEY
  5. 同 4，但 ATT_KEY 不存在 → 看抛什么异常
  6. 故意触发 401（用错 api_key）→ 看 pyzotero 抛什么异常类型（对照 §10.0.2.6）

- [ ] **Step 2**：写 `docs/superpowers/specs/spikes/pyzotero-attachment-api.md`，结构：
  ```markdown
  # pyzotero attachment API spike — 2026-06-07

  ## 测试环境
  - pyzotero version: ___
  - test library_id: ___（personal）
  - parent item key: ___

  ## 结果汇总（与设计 §10.0.2.1 对照）
  | API | 设计假设 | 实测结果 | 一致性 |
  ...

  ## respx 覆盖性结论
  - 是否拦截到 pyzotero 的 httpx 请求？___
  - 是否拦截到 webdav4？___（spike 范围内可能 N/A，留空待阶段 4）
  - 决策：[respx | adapter mock]

  ## 异常类型实测
  | 触发条件 | pyzotero 异常 class | 对应 §10.0.2.6 行 | 一致？ |
  ...

  ## 与设计冲突项（如有）
  ...
  ```

- [ ] **Step 3**：**如果实测与设计 §10.0.2 冲突**：halt，先在主分支提 PR 修订设计文档相关章节，等 reviewer 确认后再继续 Task 2。**禁止**绕过设计冲突直接实施。

- [ ] **Step 4**：commit
  ```
  docs(spike): record pyzotero attachment API findings
  ```
  注：`_spike.py` 不入库（在 `.gitignore` 中已覆盖一次性脚本）。

---

## Task 2: adapters/zotero_api.py — ZoteroAPI 基础与连接

**Files:**
- Create: `src/zotero_cli/adapters/__init__.py`
- Create: `src/zotero_cli/adapters/zotero_api.py`
- Create: `tests/unit/test_zotero_api.py`

**Key tests:**
- `test_zotero_api_init_user_library`：`ZoteroAPI(profile)` 构造时调 `pyzotero.Zotero(library_id, library_type, api_key)`，参数对应 profile 字段
- `test_zotero_api_init_group_library`：`library_type="group"` 透传
- `test_zotero_api_invalid_api_key_raises_invalid_api_key`：mock 401 → 抛 `InvalidApiKeyError`
- `test_zotero_api_holds_zotero_instance_for_reuse`：同一实例多次调用复用底层 `Zotero` 对象（不重连）

**Implementation**（参考设计 §3 / §10.0.2 / §10.0.2.6 + Task 1 spike 结论）：
```python
from pyzotero.zotero import Zotero
from zotero_cli.models.config import ProfileConfig
from zotero_cli.models.errors import CLIError


class ZoteroAPI:
    """Thin wrapper around pyzotero. Holds one Zotero instance per profile.
    All methods translate pyzotero exceptions via _map_pyzotero_exception (Task 3)."""

    def __init__(self, profile: ProfileConfig) -> None:
        self._profile = profile
        self._zot = Zotero(
            library_id=profile.library_id,
            library_type=profile.library_type,
            api_key=profile.api_key,
        )

    @property
    def library_id(self) -> str:
        return self._profile.library_id
```

**Steps:**
- [ ] 写测试（mock pyzotero.Zotero via pytest-mock）
- [ ] 跑测试确认失败
- [ ] 写实现
- [ ] 跑测试 + ruff + mypy
- [ ] commit `feat(zotero_api): add ZoteroAPI wrapper holding pyzotero.Zotero instance`

---

## Task 3: adapters/zotero_api.py — `_map_pyzotero_exception` 翻译表

**Files:**
- Modify: `src/zotero_cli/adapters/zotero_api.py`
- Modify: `tests/unit/test_zotero_api.py`

**Goal**：实现设计 §10.0.2.6 翻译表的纯函数 `_map_pyzotero_exception(exc) -> CLIError`，供 adapter 层所有方法的 try/except 复用。**所有 pyzotero 抛错都过这一道**——service 层不再翻译。

**Key tests**（参数化覆盖 §10.0.2.6 全部行）：
- `(FileDoesNotExist, FileNotFoundCLIError, "FILE_NOT_FOUND")`
- `(ParamNotPassedError, MissingRequiredArgError, "MISSING_REQUIRED_ARG")`
- `(UnsupportedParamsError, MutuallyExclusiveArgsError, "MUTUALLY_EXCLUSIVE_ARGS")`
- `(TooManyRequestsError, ApiRateLimitError, "API_RATE_LIMIT")`
- `(RequestEntityTooLargeError, StorageQuotaExceededError, "STORAGE_QUOTA_EXCEEDED")`
- `(PreConditionFailedError, ApiServerError, "API_SERVER_ERROR")`
- `(UploadError, NetworkError, "NETWORK_ERROR")`（含底层 timeout 时再分 → `ApiTimeoutError`）
- `(UserNotAuthorisedError 401, InvalidApiKeyError, "INVALID_API_KEY")`
- `(UserNotAuthorisedError 403, InsufficientPermissionsError, "INSUFFICIENT_PERMISSIONS")`
- 未识别异常 → 包装成 `CLIError("...", cause=exc)`，保留原异常便于排查
- `test_translated_error_carries_cause`：原异常进 `CLIError.cause`

**Implementation skeleton**：
```python
from pyzotero import zotero_errors as zerr
from zotero_cli.models.errors import (
    FileNotFoundCLIError, MissingRequiredArgError, MutuallyExclusiveArgsError,
    ApiRateLimitError, StorageQuotaExceededError, ApiServerError,
    NetworkError, ApiTimeoutError, InvalidApiKeyError, InsufficientPermissionsError,
    CLIError,
)

def _map_pyzotero_exception(exc: Exception) -> CLIError:
    # 按 isinstance 链匹配，先具体后泛化
    if isinstance(exc, zerr.FileDoesNotExist):
        return FileNotFoundCLIError(str(exc), cause=exc)
    # ...
    return CLIError(f"unmapped pyzotero error: {exc!r}", cause=exc)
```

**Steps:**
- [ ] 参数化测试
- [ ] 失败 → 实现 → 通过 → ruff + mypy
- [ ] commit `feat(zotero_api): add _map_pyzotero_exception per design §10.0.2.6`

---

## Task 4: adapters/zotero_api.py — `_select_backend`

**Files:**
- Modify: `src/zotero_cli/adapters/zotero_api.py`
- Modify: `tests/unit/test_zotero_api.py`

**Goal**：实现设计 §10.0.2 入口判定函数。模块级私有函数（不挂在 `ZoteroAPI` 类上，方便阶段 4 `attachment_service.py` 直接调）。

**Key tests:**
- `test_select_backend_no_webdav_returns_zfs`：`profile.webdav is None` → `"zfs"`
- `test_select_backend_with_webdav_returns_webdav`：`profile.webdav` 不为 None → `"webdav"`
- `test_select_backend_return_type_is_literal`：mypy 检查（运行时只需断言字符串）

**Implementation**（设计 §10.0.2 lines 734-737）：
```python
from typing import Literal
from zotero_cli.models.config import ProfileConfig


def _select_backend(profile: ProfileConfig) -> Literal["zfs", "webdav"]:
    return "webdav" if profile.webdav is not None else "zfs"
```

- [ ] 测试 → 失败 → 实现 → 通过 → ruff + mypy
- [ ] commit `feat(zotero_api): add _select_backend dispatcher per design §10.0.2`

---

## Task 4a: models/results.py — service 返回类型

**Files:**
- Create: `src/zotero_cli/models/results.py`
- Test: `tests/unit/test_results_models.py`

> **回应 review P2 Issue 7**：DEVELOPMENT.md §4.2 禁止裸 `dict[str, Any]` 作为对外返回。所有 service 的公开方法必须用 `TypedDict` 标注 shape。本任务集中定义全部结果类型，后续 Task 5-12 直接引用。

**对外类型**：

```python
"""Service-layer result types. All Item/Collection/Tag/Export services return
these TypedDicts (no bare dict[str, Any]).

Per design §8.1 / §8.2 / §7.2.1: services return (data, meta_extra) split, where
data goes into envelope.data and meta_extra is merged into envelope.meta.
"""
from __future__ import annotations
from typing import Any, NotRequired, TypedDict


# --- Read operations (list / search / show) ---

class ListMetaExtra(TypedDict, total=False):
    count: int
    total: int
    limit: int
    start: int
    next_start: int | None
    library_id: str
    library_version: int


class ListServiceResult(TypedDict):
    data: list[dict[str, Any]]   # raw zotero item dicts (dynamic schema, see note)
    meta_extra: ListMetaExtra


class ShowServiceResult(TypedDict):
    data: dict[str, Any]         # single raw zotero item dict
    meta_extra: NotRequired[dict[str, Any]]  # 空或不出现


# --- Write operations (create / update / delete / attach) ---

class MutationSuccessfulItem(TypedDict):
    index: int
    key: str
    version: int
    data: NotRequired[dict[str, Any]]


class MutationUnchangedItem(TypedDict):
    index: int
    key: str


class MutationFailedItem(TypedDict):
    index: int
    code: str
    message: str
    context: NotRequired[dict[str, Any]]


class MutationData(TypedDict):
    successful: list[MutationSuccessfulItem]
    unchanged: list[MutationUnchangedItem]
    failed: list[MutationFailedItem]


class MutationMetaExtra(TypedDict, total=False):
    affected_keys: list[str]
    library_id: str


class MutationServiceResult(TypedDict):
    data: MutationData
    meta_extra: MutationMetaExtra


# --- Dry-run ---

class DryRunData(TypedDict, total=False):
    dry_run: bool
    would_create: list[dict[str, Any]]
    would_update: list[dict[str, Any]]
    would_delete: list[str]
    would_upload: list[dict[str, Any]]


class DryRunServiceResult(TypedDict):
    data: DryRunData
    meta_extra: NotRequired[dict[str, Any]]


# --- Export (raw bytes / text) ---

class ExportServiceResult(TypedDict):
    """Raw export content; command layer writes to stdout or --output file."""
    data: bytes                  # 原始字节（bibtex / ris / csljson 文本）
    meta_extra: NotRequired[dict[str, Any]]


# --- Collections tree (mode=TREE) ---

class CollectionNode(TypedDict):
    """Recursive collection tree node, used by `collections list` (mode=TREE).

    children 是同类节点；最终 envelope.data 是 list[CollectionNode]
    （顶级集合数组），子节点收敛在每个 CollectionNode.children 内。
    """
    key: str
    name: str
    items_count: int
    parent_key: str | None       # None = top-level
    children: list["CollectionNode"]


class CollectionTreeServiceResult(TypedDict):
    data: list[CollectionNode]
    meta_extra: NotRequired[dict[str, Any]]
```

**关于 `dict[str, Any]` 的边界例外**：
- `data: list[dict[str, Any]]` 中的内层 dict 是 **Zotero API 直接返回的 item dicts**——其 schema 是 Zotero 服务端动态决定（不同 itemType 字段不同，外加 `links` / `meta` 等），不在我们的"对外返回"语义里。这种"外部数据透传"允许保留 `dict[str, Any]`。
- 我们自己定义的封装层（envelope / service result）必须用 TypedDict。

> **回应 review P2 Issue 7（TypedDict 贯彻）**：collections / tags / items 所有公开 service 方法都已在本任务的 `models/results.py` 提供对应 TypedDict（`ListServiceResult` / `ShowServiceResult` / `MutationServiceResult` / `DryRunServiceResult` / `ExportServiceResult` / `CollectionTreeServiceResult`）。后续 Task 5-12 的方法签名一律用这些类型，**不**写 `-> dict`。

**Key tests**：

```python
from zotero_cli.models.results import (
    ListServiceResult, MutationServiceResult, MutationFailedItem,
)


def test_list_service_result_required_fields() -> None:
    r: ListServiceResult = {
        "data": [{"key": "ABC"}],
        "meta_extra": {"count": 1, "total": 1, "limit": 100, "start": 0,
                       "next_start": None},
    }
    assert r["data"][0]["key"] == "ABC"
    assert r["meta_extra"]["count"] == 1


def test_mutation_failed_item_optional_context() -> None:
    f: MutationFailedItem = {"index": 0, "code": "E", "message": "m"}
    assert "context" not in f


def test_mutation_service_result_split() -> None:
    r: MutationServiceResult = {
        "data": {"successful": [{"index": 0, "key": "X", "version": 1}],
                 "unchanged": [], "failed": []},
        "meta_extra": {"affected_keys": ["X"]},
    }
    assert r["data"]["successful"][0]["key"] == "X"
    assert r["meta_extra"]["affected_keys"] == ["X"]
```

**Steps**：写测试 → 失败 → 写 TypedDict 定义 → 通过（mypy strict 必须通过；TypedDict 测试主要靠 mypy 把关）→ commit `feat(models): add service result TypedDicts (no bare dict[str, Any] returns)`

---

## Task 5: services/item_service.py — list / search / show

**Files:**
- Create: `src/zotero_cli/services/__init__.py`（如未存在）
- Create: `src/zotero_cli/services/item_service.py`
- Create: `tests/unit/test_item_service.py`

**Goal**：`ItemService.list(...)` / `.search(query, ...)` / `.show(key, ...)` 返回 envelope-ready dict。Service 层只组装数据，不格式化（设计 §7.1）。

**Adapter 扩展**（同步在 `zotero_api.py` 加方法，每个都包 `_map_pyzotero_exception`；公开签名用 `PyzoteroResponse: TypeAlias = dict[str, Any]` alias，遵循 DEVELOPMENT.md §4.2 adapter boundary 例外）：
- `items(limit, start, collection=None, tag=None) -> list[PyzoteroResponse]`
- `items_top(limit, start) -> list[PyzoteroResponse]`（list 默认排除 attachment / note 子项）
- `search_items(query, limit, start) -> list[PyzoteroResponse]`
- `item(key) -> PyzoteroResponse`（404 → `ItemNotFoundError`）
- `top_count() -> int` / `count_items(filters) -> int`（用 `Total-Results` header；pyzotero 暴露 `last_modified_version` / `num_items()`）

**Key tests**（service 层用 pytest-mock patch `ZoteroAPI` 方法）：
- `test_list_returns_envelope_data_with_meta_count`：list[dict] + `meta_extra={"count":..., "total":..., "library_id":..., "library_version":...}`
- `test_list_filters_by_collection`：`collection="COLL1"` 透传到 adapter
- `test_list_with_tag_filter`
- `test_search_passes_query_to_adapter`
- `test_show_404_propagates_item_not_found`：adapter 抛 `ItemNotFoundError` → service 不捕获，直接透传
- `test_show_attaches_collection_names`（如设计要求；否则跳过）

**Implementation**：
```python
from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.models.results import ListServiceResult, ShowServiceResult


class ItemService:
    def __init__(self, api: ZoteroAPI) -> None:
        self._api = api

    def list(self, *, limit: int = 100, start: int = 0,
             collection: str | None = None, tag: str | None = None) -> ListServiceResult:
        items = self._api.items_top(limit=limit, start=start, collection=collection, tag=tag)
        total = self._api.count_items(collection=collection, tag=tag)
        return {
            "data": items,
            "meta_extra": {
                "count": len(items), "total": total, "limit": limit, "start": start,
                "next_start": start + limit if start + limit < total else None,
                "library_id": self._api.library_id,
                "library_version": self._api.last_modified_version(),
            },
        }

    def show(self, key: str) -> ShowServiceResult:
        return {"data": self._api.item(key), "meta_extra": {}}
    # search 同 list 形态
```

**Steps:**
- [ ] adapter 端先加方法（含 mapping 单测）
- [ ] service 测试 → 失败 → 实现 → 通过
- [ ] ruff + mypy + commit `feat(item_service): add list/search/show with envelope meta`

---

## Task 6: services/item_service.py — create + create_single（单条 + `--json-file` 批量）

**Files:**
- Modify: `src/zotero_cli/services/item_service.py`
- Modify: `tests/unit/test_item_service.py`

**Goal**：提供两个写入入口，避免后续复合命令误用 batch 返回值：
- `ItemService.create(payloads: list[dict[str, Any]]) -> MutationServiceResult` 返回设计 §8.2 batch 形态（公开方法签名用 `models/results.py` 的 TypedDict；DEVELOPMENT.md §4.2）。它允许 `failed[]` 非空，并把每条失败作为 per-item failure 返回。
- `ItemService.create_single(payload: dict[str, Any]) -> MutationSuccessfulItem` 只用于命令层需要"父 item 必须创建成功才能继续"的场景（Phase 4 `items create --attach`）。它调用 `create([payload])`，若 `failed[]` 非空或 `successful[]` 为空，必须抛标准 `CLIError`，满足设计 §10.0.2.5 A1"父 item 创建失败直接报错"。

```python
# MutationServiceResult shape:
{
  "data": {"successful": [...], "unchanged": [...], "failed": [...]},
  "meta_extra": {"affected_keys": [...]},  # §7.2.1 规则：仅 successful 进
}
```

**Adapter 扩展**：`create_items(payloads: list[PyzoteroTemplate]) -> PyzoteroResponse`（公开签名用 alias；pyzotero `create_items` 返回 `{successful, unchanged, failed, success}` 结构；本 adapter 把它规范化为 `{successful, unchanged, failed}` 列表，每项含 `index/key/version/data` 或 `index/code/message/context`）。

**Payload 来源**（command 层组装，service 不关心来源）：
- 单条：`items create --type T --title X` → 一项 payload（item_template 填充字段）
- 批量：`--json-file path` → 文件解析为 `list[PyzoteroTemplate]`，逐项进 adapter

**Key tests:**
- `test_create_batch_single_success_returns_successful`：mock adapter 返 1 successful → `affected_keys=["KEY"]`
- `test_create_batch_mixed_results`：3 个 payload，1 成功 + 1 unchanged + 1 失败 → `affected_keys` 仅含 successful 的 key
- `test_create_invalid_item_type_in_batch_does_not_abort`：`failed[]` 含 `INVALID_ITEM_TYPE` 项，其他 successful 正常
- `test_create_pyzotero_exception_translates`：adapter 抛 `ApiServerError` → 透传到 service 调用方（不吞）
- `test_create_single_returns_first_successful_item`：mock `create([payload])` 返 1 successful → 返回该 successful item（不是整个 `MutationServiceResult`）
- `test_create_single_failed_item_raises_registered_cli_error`：mock `create([payload])` 返 `successful=[]`、`failed=[{"code":"INVALID_ITEM_TYPE", "message":"bad type", "context":{"item_type":"bad"}}]` → 抛 `InvalidItemTypeError`，`context` 保留
- `test_create_single_empty_successful_and_failed_raises_api_server_error`：mock `create([payload])` 返空 successful + 空 failed → 抛 `ApiServerError`，避免命令层 `successful[0]` 变 `IndexError`

**Implementation**：
```python
from typing import Any

from zotero_cli.models.errors import ApiServerError, from_code
from zotero_cli.models.results import MutationServiceResult, MutationSuccessfulItem


def create(self, payloads: list[dict[str, Any]]) -> MutationServiceResult:
    result = self._api.create_items(payloads)  # 已规范化为 {successful, unchanged, failed}
    affected = [s["key"] for s in result["successful"]]
    return {
        "data": result,
        "meta_extra": {"affected_keys": affected},
    }


def create_single(self, payload: dict[str, Any]) -> MutationSuccessfulItem:
    result = self.create([payload])
    data = result["data"]
    if data["successful"]:
        return data["successful"][0]
    if data["failed"]:
        failed = data["failed"][0]
        raise from_code(
            failed["code"],
            failed["message"],
            context=failed.get("context"),
        )
    raise ApiServerError(
        "Zotero create returned no successful or failed item",
        context={"payload_count": 1},
    )
```

**Steps**：adapter 规范化函数 → service `create` 包装 → `create_single` 失败语义测试 → 实现 → commit `feat(item_service): add create_single helper for single-item write commands`

---

## Task 7: services/item_service.py — update + delete

**Files:**
- Modify: `src/zotero_cli/services/item_service.py`
- Modify: `tests/unit/test_item_service.py`

**Goal**（公开方法签名用 `models/results.py` 的 TypedDict；DEVELOPMENT.md §4.2）：
- `update(key, patch: dict[str, Any]) -> MutationServiceResult`：拉当前 item → 应用 patch（含 `--add-tags` 合并、`--json-patch` 浅合并）→ pyzotero `update_item(item)`。返回 `{"data": MutationData(successful=[{index, key, version, data}], unchanged=[], failed=[]), "meta_extra": {"affected_keys": [key]}}`（即便单条也用 batch 形态，envelope 一致）。
- `delete(keys: list[str]) -> MutationServiceResult`：pyzotero `delete_item(...)` 逐个调（pyzotero 单条 API），失败按 §7.2.1 规则。`affected_keys` 含**所有删除成功**的 key（即便服务端原本不存在也算成功，因为最终态一致）。

**Adapter 扩展**：`update_item(item) / delete_item(item)`（pyzotero 接口要求传整个 item dict 含 `version`，service 负责先 `get` 再 patch）。

**Key tests:**
- `test_update_single_field_uses_existing_version`：先 mock adapter `item(KEY)` → 拿 version → patch → mock `update_item` 收到含 `version` 的 dict
- `test_update_add_tags_merges_with_existing`：原 tags `[A,B]` + add `[C]` → 最终 `[A,B,C]`（按 §6 命令树 `--add-tags` 语义）
- `test_update_replace_tags_overrides`：`--tags X,Y` → 完全替换为 `[{tag:X},{tag:Y}]`
- `test_update_json_patch_shallow_merge`：`--json-patch '{"abstractNote":"new"}'` → 仅改一字段
- `test_delete_multi_keys_returns_all_in_successful`
- `test_delete_404_treated_as_unchanged_or_successful`：根据 spike 结论决定（如 pyzotero 404 抛 `ItemNotFoundError`，则归 `failed[]`；若静默成功，归 `successful[]`）

**Implementation**：
```python
def update(self, key: str, *, patch: dict[str, Any]) -> MutationServiceResult:
    item = self._api.item(key)
    merged = _apply_patch(item["data"], patch)
    item["data"] = merged
    self._api.update_item(item)
    return {
        "data": {"successful": [{"index": 0, "key": key,
                                  "version": item["version"] + 1, "data": merged}],
                 "unchanged": [], "failed": []},
        "meta_extra": {"affected_keys": [key]},
    }


def delete(self, keys: list[str]) -> MutationServiceResult:
    # ... per-key delete; aggregate into MutationData
    ...
```
（`_apply_patch` 是模块私有辅助，处理 add-tags / replace-tags / json-patch 合并语义。）

**Steps**：adapter 测试 → service 测试 → 实现 → commit `feat(item_service): add update and delete with patch merge semantics`

---

## Task 8: commands/items.py — list / search / show

**Files:**
- Create: `src/zotero_cli/commands/__init__.py`
- Create: `src/zotero_cli/commands/items.py`
- Create: `tests/integration/test_items_commands.py`

**Goal**：Typer subapp `app = typer.Typer()`，三个只读命令。命令层职责（**全部经 `run_command`**，本模块自己**不写** try/except CLIError，更不直接 `typer.echo` 写 stderr）：

1. 解析 Typer 参数 → 从 `ctx.obj` 取 `GlobalOptions`（`profile` / `json_mode` / `quiet` 属性访问）
2. 闭包 `work` 内：调 `load_config(profile=ctx.obj.profile)` → 构造 `ZoteroAPI` + `ItemService` → 调 service → 返回 service 的 `data`（list / dict）
3. 调 `run_command(command="items.list", mode=OutputMode.KV_LIST, options=ctx.obj, work=work, meta_extra=..., field_filter=...)`：runner 处理 envelope 构造、stdout/stderr 分离、exit code（设计 §7.5）

**Mode 映射**（设计 §7.2）：
- `list` / `search` → `OutputMode.KV_LIST`
- `show` → `OutputMode.KV`

**field_filter 规则**：
- `--all-fields` 传入 → field_filter=None（全字段）
- 否则 → field_filter = `load_config(profile).item_fields.list`

**Key tests**（用 `typer.testing.CliRunner`）：
- `test_items_list_default_kv_list`：runner.invoke(app, ["list"]) → stdout 含 `key: ...`、`title: ...`，stderr 空
- `test_items_list_json_returns_envelope`：`--json` → stdout 解析为 envelope，`ok=true`、`meta.command=="items.list"`，stderr 空
- `test_items_list_quiet_only_keys`：`--quiet` → 每行一个 key，stderr 空
- `test_items_show_not_found_exit_1`：mock service 抛 `ItemNotFoundError` → 退出码 1，**stderr 含 `ITEM_NOT_FOUND`，stdout 空**（设计 §7.5 默认模式分离）
- `test_items_show_not_found_json_mode_writes_envelope_to_stdout`：`--json` 模式下错误也走 stdout（envelope `ok=false`），stderr 空
- `test_items_search_with_limit`
- `test_items_show_all_fields_overrides_filter`：`--all-fields` 跳过 `[<profile>.item_fields] list` 过滤

**Implementation skeleton**：
```python
import typer
from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.services.item_service import ItemService
from zotero_cli.services.config_service import load_config
from zotero_cli.commands._runner import GlobalOptions, run_command
from zotero_cli.utils.output import OutputMode

app = typer.Typer(help="Item operations")


@app.command("list")
def list_items(
    ctx: typer.Context,
    limit: int = typer.Option(100, "--limit"),
    collection: str | None = typer.Option(None, "--collection"),
    tag: str | None = typer.Option(None, "--tag"),
    all_fields: bool = typer.Option(False, "--all-fields"),
) -> None:
    options: GlobalOptions = ctx.obj
    profile = load_config(profile=options.profile, config_path=options.config_path)
    field_filter = None if all_fields else profile.item_fields.list

    def work():
        api = ZoteroAPI(profile)
        svc = ItemService(api)
        result = svc.list(limit=limit, collection=collection, tag=tag)
        return result["data"], result["meta_extra"]

    # 小适配：work 拆 data 与 meta_extra
    def work_data():
        d, _ = work()
        return d
    # 实际实现里更优雅的写法：work 直接返回 data，meta_extra 通过另一个机制传递；
    # 这里为简洁，让 work 返回 data 并预先拿 meta_extra（首次调用前用一个共享变量）。
    # 实现见下方完整 _invoke 辅助。
    _invoke(ctx, "items.list", OutputMode.KV_LIST, work, field_filter=field_filter)
```

完整 `_invoke` helper（模块私有，所有 7 个子命令复用；放在 `commands/items.py` 顶部）：

```python
from typing import Any, Callable

def _invoke(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    work: Callable[[], tuple[Any, dict[str, Any] | None]],
    *,
    field_filter: list[str] | None = None,
) -> None:
    """Wrap work in run_command. work returns (data, meta_extra) tuple.
    Cache the meta_extra inside the closure handed to run_command."""
    captured_meta: dict[str, Any] = {}

    def runner_work() -> Any:
        data, meta_extra = work()
        if meta_extra:
            captured_meta.update(meta_extra)
        return data

    run_command(
        command=command, mode=mode, options=ctx.obj,
        work=runner_work, meta_extra=captured_meta,
        field_filter=field_filter,
    )
```

> **架构纪律**：本模块**不**写 `try/except CLIError`、**不**调 `typer.echo` 输出 stderr、**不**调 `sys.exit`。所有这些都委托给 `run_command`。

**Steps**：CliRunner fixture → 测试 → 失败 → 实现 → ruff + mypy → commit `feat(items): add list/search/show commands via run_command`

---

## Task 9: commands/items.py — create / update / delete（接 audit_log）

**Files:**
- Modify: `src/zotero_cli/commands/items.py`
- Modify: `tests/integration/test_items_commands.py`

**Goal**：写操作 + 审计日志。Mode 全部 `OutputMode.SUMMARY`。

**审计日志 hook 点**（设计 §9.4 / DEVELOPMENT.md §10.2）：
- 在 `_run` helper（或新增 `_run_write`）的 service 调用前后切片：
  - 成功：`AuditEntry(result="success", affected_keys=[...], ...)`
  - 失败：`AuditEntry(result="failure", error_code=err.code, error_message=err.message, ...)`
- `args` 字段填命令行原始参数 dict（敏感字段由 `audit_log._mask_args` 兜底，但本层应主动剔除 `--api-key` 等不该入参的字段）
- `timestamp` 用 `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
- `log_path` 取自 `~/.local/state/zotero-cli/audit.log`（环境变量 `XDG_STATE_HOME` 优先；测试用 `monkeypatch` 重定向）

**子命令**（**不含 `--attach` / `--attach-title`**——属于阶段 4）：
- `create --type T --title X [--creators JSON] [--date D] [--doi DOI] [--url URL] [--tags T1,T2] [--collection KEY] [--json-file PATH] [--dry-run]`
- `update <key> [--title T] [--date D] [--tags T1,T2] [--add-tags T] [--json-patch JSON] [--dry-run]`
- `delete <key>... [--yes] [--dry-run]`

**Key tests:**
- `test_create_single_writes_audit_entry`：`tmp_audit_log` fixture → invoke create → 检查 JSONL 含 `command="items.create"`、`result="success"`、`affected_keys=[...]`
- `test_create_failure_writes_audit_entry`：mock adapter 抛 `ApiTimeoutError` → audit 含 `result="failure"`、`error_code="API_TIMEOUT"`
- `test_create_dry_run_returns_would_create_and_does_not_write_audit`：`--dry-run` → stdout data 含 `dry_run=true` + `would_create=[...]`，audit 0 行
- `test_update_dry_run_returns_would_update_and_does_not_write_audit`：`--dry-run` → stdout data 含 `would_update=[{"key": key, "patch": patch}]`，audit 0 行
- `test_create_quiet_outputs_keys`：`--quiet` → stdout 严格等于 `affected_keys`，每行一个
- `test_update_with_add_tags_merges`：集成测试覆盖 §6 命令树 add-tags 语义
- `test_delete_multi_keys_with_yes`
- `test_delete_without_yes_prompts`（Typer confirm）

**Implementation**：写操作版本 `_invoke_write` 在 `_invoke` 基础上加 audit hook，但**不自己处理错误流向**——CLIError 写完 audit 后 `raise` 让 `run_command` 渲染：

```python
WriteActionResult = tuple[Any, dict[str, Any] | None]
DryRunActionResult = tuple[Any, dict[str, Any] | None]


def _invoke_write(
    ctx: typer.Context,
    command: str,
    mode: OutputMode,
    action: Callable[[], WriteActionResult],
    *,
    args_for_audit: dict[str, Any],
    dry_run: bool = False,
    dry_run_data: Callable[[], DryRunActionResult] | None = None,
) -> None:
    options: GlobalOptions = ctx.obj
    log_path = audit_log_path()
    captured_meta: dict[str, Any] = {}

    def wrapped() -> Any:
        start_ns = time.perf_counter_ns()
        try:
            if dry_run:
                if dry_run_data is None:
                    data: Any = {"dry_run": True}
                    meta_extra: dict[str, Any] | None = {"dry_run": True}
                else:
                    data, meta_extra = dry_run_data()
                captured_meta.update(meta_extra or {"dry_run": True})
                return data
            data, meta_extra = action()
            elapsed = (time.perf_counter_ns() - start_ns) // 1_000_000
            captured_meta.update(meta_extra or {})
            write_entry(log_path=log_path, entry=AuditEntry(
                timestamp=now_iso(), profile=options.profile, command=command,
                args=args_for_audit, result="success",
                affected_keys=(meta_extra or {}).get("affected_keys", []),
                elapsed_ms=elapsed,
            ))
            return data
        except CLIError as err:
            elapsed = (time.perf_counter_ns() - start_ns) // 1_000_000
            write_entry(log_path=log_path, entry=AuditEntry(
                timestamp=now_iso(), profile=options.profile, command=command,
                args=args_for_audit, result="failure",
                affected_keys=[], elapsed_ms=elapsed,
                error_code=err.code, error_message=err.message,
            ))
            raise  # 让 run_command 渲染并 sys.exit

    run_command(
        command=command, mode=mode, options=options,
        work=wrapped, meta_extra=captured_meta,
    )
```

> **不再自己 catch CLIError、不再 typer.echo、不再 raise typer.Exit**。run_command 负责所有这些，本 helper 只做 audit 钩子。

**Steps**：测试（含 audit 文件断言 + stdout/stderr 分离断言）→ 失败 → 实现 → ruff + mypy → commit `feat(items): add create/update/delete via run_command + audit hook`

---

## Task 10: services/collection_service.py + commands/collections.py

**Files:**
- Create: `src/zotero_cli/services/collection_service.py`
- Create: `src/zotero_cli/commands/collections.py`
- Create: `tests/unit/test_collection_service.py`
- Create: `tests/integration/test_collections_commands.py`

**Adapter 扩展**：`collections() / collection(key) / create_collection(...) / update_collection(...) / delete_collection(...) / collection_items(key) / addto_collection(item, key) / deletefrom_collection(item, key)`（pyzotero 已有对应方法，名字可能不同——以 spike 结论为准）。

**Service 方法**（**所有公开方法签名必须用 `models/results.py` 的 TypedDict**，遵循 DEVELOPMENT.md §4.2 + Task 4a；下方"-> X"是实际签名，不是简写）：

- `list() -> CollectionTreeServiceResult`：返回 `OutputMode.TREE` 形态（含 `name/key/items_count/children`，递归构造树；adapter 给的是扁平 list 含 `parentCollection`，service 端组装树）。`CollectionTreeServiceResult` 是 Task 4a `models/results.py` 在本任务**新增**的 TypedDict，shape：`{"data": list[CollectionNode], "meta_extra": NotRequired[dict[str, Any]]}`，`CollectionNode = TypedDict("CollectionNode", {"key": str, "name": str, "items_count": int, "parent_key": str | None, "children": list["CollectionNode"]})`
- `show(key) -> ShowServiceResult`：单 collection 详情；`data` 是 raw pyzotero collection dict（含 `parentCollection` / `items_count`），透传外部 schema 允许保留内层 `dict[str, Any]`
- `create(name, parent=None) -> MutationServiceResult`：返 `{successful:[...], unchanged:[], failed:[]}` + `affected_keys`
- `update(key, name) -> MutationServiceResult`：同 §7.2.1 规则
- `delete(key) -> MutationServiceResult`
- `add_items(coll_key, item_keys: list[str]) -> MutationServiceResult`：**`affected_keys` = `[coll_key]`**（设计 §7.2.1 表已敲定：collections.add_items 仅 collection key 进 affected_keys，语义="我修改了哪个 collection 的成员"）。`data.successful` 仍含 item-level 的 `{index, key, version}` 列表，便于 `--json` 模式拿到细节
- `remove_items(coll_key, item_keys) -> MutationServiceResult`：同上，`affected_keys = [coll_key]`

**Key tests**（service）：
- `test_list_builds_tree_from_flat_collections`：3 个 flat dicts（A 无 parent、B parent=A、C parent=B）→ 输出树形
- `test_list_orphan_parent_falls_back_to_root`：B 的 parentCollection=NONEXIST → B 被列为 root（不抛错）
- `test_create_with_parent_passes_parentCollection`
- `test_add_items_affected_keys_is_collection_key_only`：assert `meta_extra["affected_keys"] == [coll_key]`，不含 item_keys
- `test_remove_items_affected_keys_is_collection_key_only`

**Key tests**（commands）：
- `test_collections_list_tree_output`：默认 mode=TREE
- `test_collections_create_writes_audit`
- `test_collections_add_items_quiet_outputs_single_collection_key`：`--quiet` stdout 严格 = `"COLL\n"`，不包含 item keys

**Steps**：adapter 测试 → service 测试 → command 测试 → 实现 → commit `feat(collections): add full subcommand tree with tree builder and audit hooks`

---

## Task 11: services/tag_service.py + commands/tags.py

**Files:**
- Create: `src/zotero_cli/services/tag_service.py`
- Create: `src/zotero_cli/commands/tags.py`
- Create: `tests/unit/test_tag_service.py`
- Create: `tests/integration/test_tags_commands.py`

**Adapter 扩展**：`tags() / tags_for_item(key) / add_tags(item, *tags) / delete_tags(*tags) / item_tag_replace(item, old, new)`（pyzotero 接口；rename 可能要走 "delete + add" 组合，以 spike 结论为准）。

**Service 方法**（**所有公开方法签名用 `models/results.py` 的 TypedDict**）：
- `list() -> ListServiceResult`：`data` 是 list[dict]（`{tag:str, type:int, num_items:int}`，pyzotero 透传），mode=KV_LIST。`affected_keys` 不适用（read-only）；本接口的 `meta_extra` 仅含 `count` / `total`
- `add(tag, item_keys: list[str]) -> MutationServiceResult`：循环每个 item，patch tags 字段；`affected_keys` = 实际新加了 tag 的 item key（已有则归 `unchanged`）
- `remove(tag, item_keys) -> MutationServiceResult`：同上
- `rename(old, new) -> MutationServiceResult`：调 pyzotero `delete_tags(old)` + 对所有原 item 加 new；`affected_keys` = 受影响的 item keys
- `delete(tag) -> MutationServiceResult`：删除 tag（pyzotero `delete_tags`），返 `affected_keys` = 之前持有该 tag 的 item keys

**Key tests:**
- `test_list_returns_kv_list_format`
- `test_add_to_already_tagged_item_goes_to_unchanged`
- `test_rename_preserves_item_count`
- `test_delete_with_yes`
- `test_remove_404_item_in_failed_list`

**Steps**：adapter → service → command → 测试 → ruff + mypy → commit `feat(tags): add full subcommand tree with rename composition`

---

## Task 12: services/export_service.py + commands/items.py 的 export 子命令

**Files:**
- Create: `src/zotero_cli/services/export_service.py`
- Modify: `src/zotero_cli/commands/items.py`（追加 export 子命令）
- Create: `tests/unit/test_export_service.py`
- Modify: `tests/integration/test_items_commands.py`

**Adapter 扩展**：`export_items(format: str, collection: str | None, tag: str | None) -> str`（pyzotero `items(format=..., content=...)` 支持 BibTeX/RIS/CSL JSON 等）。

**Service 方法**：
- `export(format: str, *, collection: str | None = None, tag: str | None = None) -> ExportServiceResult`：返回 `{"data": <bytes>, "meta_extra": {"format": ..., "byte_size": ...}}`（`ExportServiceResult` 已在 Task 4a `models/results.py` 定义）。

**支持格式**（设计 §6 命令树 + Zotero API）：`bibtex` / `ris` / `csljson` / `bibliography` 等（以 pyzotero 实际支持为准，spike 时顺便确认）。

**Command 行为**（与设计 §7.2 export 行严格一致；本任务**不**新增"§7.2 没有的行为"）：

| 模式 | stdout 输出 | 退出码 |
|---|---|---|
| 默认 | service 返回的原始字节直接写 stdout（或 `--output FILE` 时写文件，stdout 仅打印 1 行 `Exported N items to FILE` 到 stderr） | 0 / 1-4 |
| `--json` | envelope JSON：`{"ok": true, "data": {"format":"bibtex","content":"<utf-8 string>","byte_size":<int>}, ...}` | 0 / 1-4 |
| `--quiet` | **拒绝**：`MutuallyExclusiveArgsError("--quiet is not supported for export, ...")` | 64 |

> **回应 review P2 Issue 1**：原版同时写"0 字节"和"`MUTUALLY_EXCLUSIVE_ARGS`"是矛盾。修订后：`--quiet` 走拒绝路径，与设计 §7.2 export 行 + yaml 行同档。
>
> **回应 review P1 Issue 3（作用域 bug）**：原版 `_emit_failure` 只在第一个分支内 import，第二个 `--quiet` 分支与 `except CLIError` 都会触发 `NameError` / `UnboundLocalError`。同时 `_emit_failure` 是私有 API。修订后：① 在 callback 顶部一次 import 公开 helper `emit_failure`（Phase 2 Task 6b 已公开；helper 命名去掉下划线）；② 把"调 service + 渲染"包到一个内部 `_do_export(...)` 函数里，保持单一控制流；③ 失败路径全部走 `emit_failure`，作用域无歧义。

**实现要点**（不复用 OutputMode 的 6 种值——export 是独立行为；本 callback 自己处理 mutex 和输出，但 stdout/stderr 分离规则与 `run_command` 一致）：

```python
import sys
import time
from pathlib import Path
from typing import NoReturn

import typer

from zotero_cli.adapters.zotero_api import ZoteroAPI
from zotero_cli.commands._runner import GlobalOptions, emit_failure
from zotero_cli.models.envelope import Envelope
from zotero_cli.models.errors import CLIError, MutuallyExclusiveArgsError
from zotero_cli.models.results import ExportServiceResult
from zotero_cli.services.config_service import load_config
from zotero_cli.services.export_service import ExportService


@app.command("export")
def cmd_export(
    ctx: typer.Context,
    format: str = typer.Option(..., "--format", help="bibtex / ris / csljson / ..."),
    collection: str | None = typer.Option(None, "--collection"),
    tag: str | None = typer.Option(None, "--tag"),
    output: Path | None = typer.Option(None, "--output", help="Write to file instead of stdout."),
) -> None:
    options: GlobalOptions = ctx.obj
    _export_main(options, format=format, collection=collection, tag=tag, output=output)


def _export_main(
    options: GlobalOptions,
    *,
    format: str,
    collection: str | None,
    tag: str | None,
    output: Path | None,
) -> NoReturn:
    """Export command body. Single function = single control flow.

    Validates mutex first, then delegates service call to _do_export, then
    routes output. Any CLIError from any phase goes through emit_failure +
    sys.exit. emit_failure is imported once at module top (no local-scope
    bug from review P1 Issue 3).
    """
    # 1) Mutex 校验（设计 §7.2 export 行：--quiet 不支持）
    if options.json_mode and options.quiet:
        err = MutuallyExclusiveArgsError(
            "--json and --quiet cannot be combined",
            hint="Use --json for full envelope, --quiet for affected_keys only.",
        )
        emit_failure(err, "items.export", 0, options)
        sys.exit(err.exit_code)
    if options.quiet:
        err = MutuallyExclusiveArgsError(
            "--quiet is not supported for export",
            hint="export writes raw content; --quiet has no key concept here.",
        )
        emit_failure(err, "items.export", 0, options)
        sys.exit(err.exit_code)

    # 2) 调 service + 计时
    start = time.perf_counter()
    try:
        result = _do_export(options, format=format, collection=collection, tag=tag)
    except CLIError as err:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        emit_failure(err, "items.export", elapsed_ms, options)
        sys.exit(err.exit_code)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # 3) 渲染（json envelope 或 raw bytes）
    raw_bytes: bytes = result["data"]
    byte_size = len(raw_bytes)

    if options.json_mode:
        env = Envelope.success(
            data={"format": format,
                  "content": raw_bytes.decode("utf-8"),
                  "byte_size": byte_size},
            command="items.export", elapsed_ms=elapsed_ms,
            meta_extra=result.get("meta_extra"),
        )
        sys.stdout.write(env.model_dump_json(indent=2) + "\n")
        sys.exit(0)

    # 默认模式：raw 输出
    if output is not None:
        output.write_bytes(raw_bytes)
        sys.stderr.write(f"Exported {byte_size} bytes to {output}\n")
    else:
        sys.stdout.buffer.write(raw_bytes)
    sys.exit(0)


def _do_export(
    options: GlobalOptions,
    *,
    format: str,
    collection: str | None,
    tag: str | None,
) -> ExportServiceResult:
    """Pure service call. Any CLIError raised here is caught by _export_main."""
    cfg = load_config(profile=options.profile, config_path=options.config_path)
    api = ZoteroAPI(cfg)
    svc = ExportService(api)
    return svc.export(format=format, collection=collection, tag=tag)  # ExportServiceResult
```

> **关键修订点回顾**：
> 1. `emit_failure` 在模块顶部 import 一次（Phase 2 Task 6b 已把 helper 公开为 `emit_failure`）。
> 2. `mutex 校验 + service 调用 + 渲染`走单一函数 `_export_main`；任何分支调 `emit_failure` 都不会 `NameError`。
> 3. 三处失败路径（json+quiet mutex / quiet alone / service CLIError）都用同一公共 helper，保证设计 §7.5 stdout/stderr 分离规则一致。
> 4. `_do_export` 拆出来：保持 service 调用的纯净，方便单测 mock。
> 5. **未来扩展点**：如果再加"非 envelope"命令，把这套抽到 `commands/_runner.py` 里成 `run_raw_command(*, command, options, work, render_default, render_json)`——但目前只 export 一个，YAGNI，先保留这个明确的私有副本。

**Key tests**：

> **回应 review P2（invoke 路径 + 真实 CLI flag）**：`export` 是 `commands/items.py` 上的 `@app.command("export")`，挂在 items subapp 下，再由顶层 `cli.py` 通过 `app.add_typer(items.app, name="items")` 接入根 CLI。**测试必须走根 CLI 入口** `from zotero_cli.cli import app`，命令路径写成 `["items", "export", ...]`；全局 flag（`--profile` / `--json` / `--quiet`）作为顶层 callback 选项放在子命令名之前。**不**用 `obj=GlobalOptions(...)` 注入 ctx.obj——那只能模拟 callback 内部状态，无法验证根 callback 真的解析到了 flag、能不能在调进 `cmd_export` 之前完成 `GlobalOptions` 构造。下面所有断言都基于 `runner.mix_stderr=False` 才能拿到独立 `stderr`（默认 mix 模式下 stderr 会并入 stdout）。

```python
import json

import pytest
from typer.testing import CliRunner

from zotero_cli.cli import app  # 根 CLI（顶层 callback 注册了 --json / --quiet / --profile）


@pytest.fixture
def runner() -> CliRunner:
    # mix_stderr=False 让 result.stderr 独立可断言（设计 §7.5 stdout/stderr 分离）
    return CliRunner(mix_stderr=False)


@pytest.fixture
def tmp_profile(monkeypatch, tmp_path):
    """Redirect default config path so `load_config(profile="default")` works inside cmd."""
    cfg = tmp_path / "c.toml"
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path", lambda: cfg,
    )
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg, {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}})
    return cfg


def test_export_default_writes_raw_bytes_to_stdout(mocker, runner, tmp_profile):
    mocker.patch("zotero_cli.services.export_service.ExportService.export",
                 return_value={"data": b"@article{...}\n", "meta_extra": {}})
    result = runner.invoke(app, ["items", "export", "--format", "bibtex"])
    assert result.exit_code == 0
    assert result.stdout == "@article{...}\n"
    assert result.stderr == ""


def test_export_json_wraps_in_envelope(mocker, runner, tmp_profile):
    mocker.patch("zotero_cli.services.export_service.ExportService.export",
                 return_value={"data": b"@article{...}", "meta_extra": {}})
    # 全局 --json 在子命令名之前；走真实根 callback 把 json_mode=True 写进 ctx.obj
    result = runner.invoke(app, ["--json", "items", "export", "--format", "bibtex"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is True
    assert parsed["data"]["format"] == "bibtex"
    assert parsed["data"]["content"] == "@article{...}"
    assert parsed["data"]["byte_size"] == 13
    assert result.stderr == ""


def test_export_quiet_rejected_with_64_default_mode_stderr(mocker, runner, tmp_profile):
    """`--quiet` 单独 → 设计 §7.2 export 行：rejected，错误走 stderr（默认模式）。"""
    spy = mocker.patch(
        "zotero_cli.services.export_service.ExportService.export",
    )
    result = runner.invoke(app, ["--quiet", "items", "export", "--format", "bibtex"])
    assert result.exit_code == 64
    assert result.stdout == ""
    assert "MUTUALLY_EXCLUSIVE_ARGS" in result.stderr
    # mutex 必须在调 service 前拒绝（设计 §7.2 + Phase 3 Task 14 的 mutex 兜底语义）
    assert spy.call_count == 0


def test_export_json_and_quiet_rejected_with_64_envelope_to_stdout(
    mocker, runner, tmp_profile,
):
    """`--json --quiet` 互斥 → 错误 envelope 走 stdout（设计 §7.5：json 模式错误也在 stdout）。"""
    spy = mocker.patch(
        "zotero_cli.services.export_service.ExportService.export",
    )
    result = runner.invoke(
        app, ["--json", "--quiet", "items", "export", "--format", "bibtex"],
    )
    assert result.exit_code == 64
    assert result.stderr == ""
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "MUTUALLY_EXCLUSIVE_ARGS"
    assert spy.call_count == 0


def test_export_output_file_writes_to_file_not_stdout(mocker, tmp_path, runner, tmp_profile):
    mocker.patch("zotero_cli.services.export_service.ExportService.export",
                 return_value={"data": b"@article{X}\n", "meta_extra": {}})
    out = tmp_path / "refs.bib"
    result = runner.invoke(
        app, ["items", "export", "--format", "bibtex", "--output", str(out)],
    )
    assert result.exit_code == 0
    assert result.stdout == ""  # raw 内容不进 stdout
    assert out.read_bytes() == b"@article{X}\n"
    assert "Exported 12 bytes" in result.stderr  # 进度提示走 stderr
```

> **架构提示**：如果某些极简 unit case 想直接绕开根 callback（比如只想测 `_export_main` 的内部分支），可以 `from zotero_cli.commands.items import app as items_app` 单独 invoke `["export", ...]` 并在 `obj=GlobalOptions(...)` 里塞 ctx.obj——但本任务的 Key tests 一律走顶层 `app`，确保 `--json` / `--quiet` flag 的解析路径也被覆盖。Phase 3 Task 14 的 `test_no_api_call_made_when_mutex_violated` 同口径。

**Steps**：先把 design §7.2 export 行同步好（已在本 review 修订完成）→ adapter → service → command → 测试 → ruff + mypy → commit `feat(export): add ExportService and items export command per §7.2 export row`

---

## Task 13: meta.affected_keys 边界参数化测试

**Files:**
- Create: `tests/unit/test_affected_keys.py`

**Goal**：跨 service 集中验证设计 §7.2.1 表的所有边界。本任务**只补测试**，不改实现——把所有 service 的 `affected_keys` 计算路径汇总成一个参数化测试矩阵，便于以后回归。

**矩阵**（参数化）：
| 操作 | adapter 返回 | 期望 affected_keys |
|---|---|---|
| `items.create` | `successful=[A,B], unchanged=[], failed=[]` | `[A,B]` |
| `items.create` | `successful=[A], unchanged=[B], failed=[C]` | `[A]` |
| `items.update` | `successful=[A], unchanged=[], failed=[]` | `[A]` |
| `items.update` | adapter 抛 `ItemNotFoundError` | 整个 envelope 是 failure，meta 无 affected_keys（或为空 list） |
| `items.delete` | `successful=[A,B], unchanged=[], failed=[]` | `[A,B]` |
| `collections.create` | `successful=[CA]` | `[CA]` |
| `collections.add_items` | item_keys=[I1,I2], 全部成功 | `[CA]`（仅 collection key，设计 §7.2.1 表）|
| `collections.remove_items` | 全部成功 | `[CA]` |
| `tags.add` | item I1 已有 tag → unchanged；I2 加上 → success | `[I2]` |
| `tags.rename` | old→new 影响 [I1,I2] | `[I1,I2]` |

**Implementation**：每行一个 `pytest.param`，service 用 `pytest-mock` patch adapter，断言 service 返回的 `meta_extra["affected_keys"]`。

**Steps:**
- [ ] 写参数化测试（≥ 12 case）
- [ ] 跑测试，全过 → commit `test(services): parametrize meta.affected_keys edge cases per §7.2.1`
- [ ] 任一 case 失败 → 修对应 service 的 affected_keys 计算 → 单独 commit 修复

---

## Task 14: --quiet / --json 互斥在 command 层兜底

**Files:**
- Modify: `src/zotero_cli/commands/items.py`、`src/zotero_cli/commands/collections.py`、`src/zotero_cli/commands/tags.py`（`_invoke` helper）
- Create: `tests/integration/test_command_mutex.py`

**Goal**：`utils/run_command` 已经在第一行做 mutex 校验（阶段 2 Task 6b 已就位）。本任务只需要确认：

- 所有 command 模块的 `_invoke` / `_invoke_write` 都通过 `run_command` 入口（不绕过）
- 写操作（create/update/delete）的 mutex 拦截发生在调 service / 网络之前——`run_command` 第一步就 raise，service / pyzotero / WebDAV 完全不会被触达

**Key tests**:
- `test_items_list_json_and_quiet_returns_64`：runner.invoke(app, ["--json","--quiet","list"]) → exit_code=64，stderr 空、stdout 是 JSON envelope（因为 json_mode=True，错误也走 stdout）
- 同上覆盖 collections / tags 各 1 个命令
- `test_no_api_call_made_when_mutex_violated`：mock pyzotero `Zotero` class 构造或 `items_top` 方法 → 验证 0 calls（证明 run_command 第一行就拦截了）

**Steps**：测试 → 失败（如确实有命令绕过 run_command）→ 修复 → 通过 → commit `test(commands): verify --json + --quiet mutex rejected before service call`

---

## Task 15: 阶段 3 整体覆盖率 + DEVELOPMENT.md §9.3 验收勾选

**Files:**
- Modify: `DEVELOPMENT.md`

- [ ] **Step 1**：跑完整自检
  ```bash
  uv run ruff check src tests
  uv run ruff format --check src tests
  uv run mypy src
  uv run pytest --cov=src/zotero_cli --cov-report=term-missing
  ```

- [ ] **Step 2**：核对覆盖率（设计 §12.4 / DEVELOPMENT.md §9.3）
  | 模块 | 目标 | 实测 |
  |---|---|---|
  | `adapters/zotero_api.py` | 90%+ | ____ |
  | `services/item_service.py` | 85%+ | ____ |
  | `services/collection_service.py` | 85%+ | ____ |
  | `services/tag_service.py` | 85%+ | ____ |
  | `services/export_service.py` | 85%+ | ____ |
  | `commands/items.py` | 70%+ | ____ |
  | `commands/collections.py` | 70%+ | ____ |
  | `commands/tags.py` | 70%+ | ____ |
  | 总体 | 85%+ | ____ |

- [ ] **Step 3**：把 DEVELOPMENT.md §9.3 的所有 `[ ]` 勾选为 `[x]`（spike + 实施两段都要勾）

- [ ] **Step 4**：spike 文档已在 Task 1 完成；如发现实施过程中又有新决策（如 `collections.add_items` 的 affected_keys 决策），追加到 spike 文档"实施期决策"段

- [ ] **Step 5**：commit
  ```
  docs: tick phase 3 acceptance checklist
  ```

阶段 3 完成。下一步进入阶段 4（附件上传 ZFS + WebDAV），见 `2026-06-07-phase-4-attachments.md`（待写）。

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

参见 `DEVELOPMENT.md §9.3`。
