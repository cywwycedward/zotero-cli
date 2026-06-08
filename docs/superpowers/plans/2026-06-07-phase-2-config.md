# 阶段 2：配置层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**：基于阶段 1 已就位的 errors/envelope/exit_codes/output 框架，搭出多 profile 的配置层。完成后 `zotero-cli config init/show/set/get/validate/profiles` 六个子命令可用，WebDAV × library_type 兼容性矩阵在 `config validate` 处强制，环境变量覆盖按 `ZOTERO_CLI_<PROFILE>_<KEY>` 生效，配置文件落盘权限 `0600`。

**Architecture**：纯 pydantic v2 + pydantic-settings + tomllib(读) / tomli-w(写)，配合 Typer 命令薄层。分层严格遵循 DEVELOPMENT.md §5：`models/config.py` 只放数据结构与校验；`adapters/config_store.py` 是唯一 I/O 层（read_toml / write_toml + 0600 / 平台路径检测）；`services/config_service.py` 纯编排（不做 I/O）；`commands/_runner.py` 是命令层共享 runner（GlobalOptions + run_command + emit_failure 公开 helper）；`commands/config.py` 通过 `_runner.run_command` 走统一的 stdout/stderr 分离。

**Tech Stack**：Python 3.11+ / pydantic v2 / pydantic-settings 2.2+ / tomllib (stdlib) / tomli-w 1.0+ / Typer 0.12+。

**Source-of-truth references**：
- 设计文档：`docs/superpowers/specs/2026-06-07-zotero-cli-design.md` §5、§6、§10.0.1、§13 阶段 2
- 协作规范：`DEVELOPMENT.md` §6 TDD、§9.2 阶段 2 acceptance checklist
- 上游依赖：阶段 1 已 commit 的 `models/errors.py`、`models/envelope.py`、`utils/exit_codes.py`、`utils/output.py`

---

## 文件结构（仅列阶段 2 新增/修改）

```
zotero-cli/
├── src/zotero_cli/
│   ├── cli.py                          # 顶层 Typer app（占位；阶段 6 完整化）
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── _runner.py                  # GlobalOptions dataclass + run_command + emit_failure（stdout/stderr 分离 + CLIError 捕获 + sys.exit）
│   │   └── config.py                   # 6 subcommands: init/show/set/get/validate/profiles
│   ├── services/
│   │   ├── __init__.py
│   │   └── config_service.py           # 纯编排：load_config / validate_profile（无 I/O）
│   ├── adapters/
│   │   ├── __init__.py
│   │   └── config_store.py             # 唯一允许碰本地配置文件的层：read_toml / write_toml / default_config_path / detect_sqlite_db
│   └── models/
│       └── config.py                   # 5 子模型 + 主 Config + 兼容性矩阵 validator
└── tests/
    └── unit/
        ├── test_config_models.py
        ├── test_config_store.py
        ├── test_config_service.py
        ├── test_config_commands.py
        └── test_command_runner.py
```

> **回应 review P1 Issue 1（utils 分层）**：runner 不在 `utils/`。它做 `sys.exit` + 写 stdout/stderr，是 CLI 命令路径的最薄包装，归 `commands/_runner.py`（DEVELOPMENT.md §5.2 已同步：commands 层允许 sys.exit + 写流；`_runner` 前缀下划线表示模块内部基础设施，不是用户面向的命令）。`utils/` 仍允许 import `models/`（DEVELOPMENT.md §5.1 已同步），所以 `utils/output.py` import `Envelope` / `CLIError` 合法——这是数据依赖、无副作用。

## 模块依赖关系

```
阶段 1 已就位：errors / envelope / exit_codes / output / audit_log

ItemFieldsConfig + FeedItemFieldsConfig（无依赖）
        ↓
WebDAVConfig（依赖 errors.ConfigInvalidError）
        ↓
SQLiteConfig（无外部依赖）
        ↓
ProfileConfig（组合上述四个 + 顶层 api_key/library_id/library_type）
        ↓
Config（dict[str, ProfileConfig] + WebDAV × library_type 矩阵 model_validator）
        ↓
adapters/config_store（read_toml / write_toml + 0600 / 路径检测）  ←  唯一 I/O 层
        ↓
config_service（纯编排：read_toml → 应用 env 覆盖 → SQLite 路径兜底 → 构造 Config → 取 profile）
        ↓
commands/_runner（GlobalOptions + run_command + emit_failure；命令层共享）
        ↓
commands/config（六子命令；init/set 通过 config_store 写盘）
```

**任务执行顺序**：Task 1 → 2 → 3 → 4 → 5 → 6 → 6a → 6b → 7 → 8 → 9 → 10 → 11。

> **架构说明**（回应 review P1 Issue 1）：DEVELOPMENT.md §5.2 禁止 services/ 写文件 I/O。本阶段把所有 TOML 读写、路径检测、文件权限设置集中到 `adapters/config_store.py`（设计 §4 已同步）。`services/config_service.py` 只做编排：收 path → 调 adapter → 应用 env 覆盖 → 调 pydantic 校验 → 返回 ProfileConfig。

---

## Task 1: ItemFieldsConfig + FeedItemFieldsConfig

**Files:**
- Create: `src/zotero_cli/models/config.py`
- Test: `tests/unit/test_config_models.py`

最小子模型：两个都只持有 `list: list[str]`，给 items list / feeds items 做字段过滤（设计 §5.2 / §7.4）。

**Key tests**:
```python
def test_item_fields_default() -> None:
    cfg = ItemFieldsConfig()
    assert cfg.list == ["key", "title", "creators", "date", "itemType", "tags"]

def test_item_fields_override() -> None:
    cfg = ItemFieldsConfig(list=["key", "title"])
    assert cfg.list == ["key", "title"]

def test_feed_item_fields_default() -> None:
    cfg = FeedItemFieldsConfig()
    assert cfg.list == ["feed_id", "item_id", "title", "date", "url", "read_time"]

def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ItemFieldsConfig(list=["k"], unknown="x")
```

**Implementation**:
```python
class ItemFieldsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list: list[str] = ["key", "title", "creators", "date", "itemType", "tags"]

class FeedItemFieldsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list: list[str] = ["feed_id", "item_id", "title", "date", "url", "read_time"]
```

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config): add ItemFieldsConfig and FeedItemFieldsConfig defaults`

---

## Task 2: WebDAVConfig + storage_path 校验器

**Files:** Modify `src/zotero_cli/models/config.py` 和 `tests/unit/test_config_models.py`

设计 §10.1 normalize 规则：空字符串 ✓；非空必须 `/` 开头；尾部 `/` 自动 strip；拒绝单 `/`、`..`、`//`。校验失败抛 `ConfigInvalidError`（注意：这里在 pydantic validator 里抛 `ValueError`，外层 `config_service` 捕获再翻成 `ConfigInvalidError`，避免 model 层依赖 errors 模块——**但** errors.py 是纯定义、无副作用，model 直接 import 也合规。本 plan 选择直接 `raise ConfigInvalidError`，保持错误码一致）。

**Key tests** (parametric)：
```python
@pytest.mark.parametrize("inp,expected", [
    ("", ""),
    ("/zotero", "/zotero"),
    ("/zotero/", "/zotero"),         # 尾部 / 自动 strip
    ("/a/b/c", "/a/b/c"),
    ("/a/b/c/", "/a/b/c"),
])
def test_storage_path_normalized(inp: str, expected: str) -> None:
    cfg = WebDAVConfig(url="https://x", username="u", password="p",
                       storage_path=inp)
    assert cfg.storage_path == expected

@pytest.mark.parametrize("bad", ["/", "//zotero", "/a//b", "/..", "/a/../b", "no-slash"])
def test_storage_path_rejected(bad: str) -> None:
    with pytest.raises(ConfigInvalidError):
        WebDAVConfig(url="https://x", username="u", password="p",
                     storage_path=bad)

def test_webdav_defaults() -> None:
    cfg = WebDAVConfig(url="https://x", username="u", password="p")
    assert cfg.storage_path == "/zotero"
    assert cfg.timeout == 120
    assert cfg.verify_ssl is True
```

**Implementation**:
```python
class WebDAVConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    storage_path: str = "/zotero"
    username: str
    password: str
    timeout: int = 120
    verify_ssl: bool = True

    @field_validator("storage_path")
    @classmethod
    def _normalize_storage_path(cls, v: str) -> str:
        if v == "":
            return v
        if not v.startswith("/"):
            raise ConfigInvalidError(
                f"storage_path must start with '/' or be empty, got: {v!r}",
                hint="Use '' for server root or '/path/to/zotero'.",
            )
        if v == "/":
            raise ConfigInvalidError(
                "storage_path cannot be '/'; use '' for server root.",
            )
        if ".." in v.split("/") or "//" in v:
            raise ConfigInvalidError(
                f"storage_path must not contain '..' or '//', got: {v!r}",
            )
        return v.rstrip("/")
```

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config): add WebDAVConfig with storage_path normalize validator (design §10.1)`

---

## Task 3: SQLiteConfig + 平台默认路径辅助

**Files:** Modify `src/zotero_cli/models/config.py`、新建 `src/zotero_cli/services/__init__.py`、新建 `src/zotero_cli/services/config_service.py`、`tests/unit/test_config_service.py`

`SQLiteConfig.path` 可空（None = 走自动检测）。自动检测放在 `services/config_service.py` 的 `detect_sqlite_path()` 辅助里（设计 §5.4 优先级）。

**Key tests**:
```python
# tests/unit/test_config_models.py
def test_sqlite_path_optional() -> None:
    cfg = SQLiteConfig()
    assert cfg.path is None

def test_sqlite_path_explicit() -> None:
    cfg = SQLiteConfig(path="/custom/zotero.sqlite")
    assert cfg.path == "/custom/zotero.sqlite"

# tests/unit/test_config_service.py
def test_detect_sqlite_explicit_wins(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
    explicit = tmp_path / "explicit.sqlite"
    explicit.touch()
    assert detect_sqlite_path(explicit_path=str(explicit)) == str(explicit)

def test_detect_sqlite_env_var_used(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
    expected = tmp_path / "zotero.sqlite"
    expected.touch()
    assert detect_sqlite_path(explicit_path=None) == str(expected)

@pytest.mark.parametrize("system,expected_suffix", [
    ("Linux", "Zotero/zotero.sqlite"),
    ("Darwin", "Zotero/zotero.sqlite"),
    ("Windows", "Zotero\\zotero.sqlite"),
])
def test_detect_sqlite_platform_default(monkeypatch, system, expected_suffix) -> None:
    monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)
    monkeypatch.setattr("platform.system", lambda: system)
    p = detect_sqlite_path(explicit_path=None)
    assert p.endswith(expected_suffix)

def test_detect_sqlite_snap_flatpak_variants_checked(monkeypatch, tmp_path) -> None:
    # Linux 下若标准路径不存在，回退到 Snap/Flatpak 路径（按存在性挑第一个）
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)
    snap = tmp_path / "snap/zotero/common/Zotero/zotero.sqlite"
    snap.parent.mkdir(parents=True)
    snap.touch()
    assert detect_sqlite_path(explicit_path=None) == str(snap)
```

**Implementation**:
```python
# models/config.py
class SQLiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None

# services/config_service.py
def detect_sqlite_path(*, explicit_path: str | None) -> str:
    """设计 §5.4: explicit → ZOTERO_DATA_DIR → platform default (Snap/Flatpak fallback)."""
    if explicit_path:
        return explicit_path
    env_dir = os.environ.get("ZOTERO_DATA_DIR")
    if env_dir:
        return str(Path(env_dir) / "zotero.sqlite")
    home = Path(os.environ.get("HOME", str(Path.home())))
    system = platform.system()
    candidates: list[Path] = []
    if system == "Linux":
        candidates = [
            home / "Zotero/zotero.sqlite",
            home / "snap/zotero/common/Zotero/zotero.sqlite",
            home / ".var/app/org.zotero.Zotero/data/Zotero/zotero.sqlite",
        ]
    elif system == "Darwin":
        candidates = [home / "Zotero/zotero.sqlite"]
    elif system == "Windows":
        userprofile = Path(os.environ.get("USERPROFILE", str(home)))
        candidates = [userprofile / "Zotero" / "zotero.sqlite"]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[0]) if candidates else str(home / "Zotero/zotero.sqlite")
```

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config): add SQLiteConfig and detect_sqlite_path helper (design §5.4)`

---

## Task 4: ProfileConfig 组合

**Files:** Modify `src/zotero_cli/models/config.py` 和 `tests/unit/test_config_models.py`

把前三个子模型 + 顶层三个字段（`api_key`、`library_id`、`library_type`）组合成 `ProfileConfig`。`webdav` 可选；其余子模型用工厂默认值。

**Key tests**:
```python
def test_profile_minimal_user() -> None:
    cfg = ProfileConfig(api_key="k", library_id="123", library_type="user")
    assert cfg.webdav is None
    assert cfg.sqlite.path is None
    assert cfg.item_fields.list[0] == "key"

def test_profile_with_webdav() -> None:
    cfg = ProfileConfig(
        api_key="k", library_id="123", library_type="user",
        webdav={"url": "https://x", "username": "u", "password": "p"},
    )
    assert cfg.webdav is not None
    assert cfg.webdav.storage_path == "/zotero"

def test_library_type_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(api_key="k", library_id="1", library_type="organization")

def test_extra_fields_rejected_at_profile_level() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(api_key="k", library_id="1", library_type="user",
                      unknown_field="x")
```

**Implementation**:
```python
class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str
    library_id: str
    library_type: Literal["user", "group"]
    webdav: WebDAVConfig | None = None
    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    item_fields: ItemFieldsConfig = Field(default_factory=ItemFieldsConfig)
    feed_item_fields: FeedItemFieldsConfig = Field(default_factory=FeedItemFieldsConfig)
```

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config): add ProfileConfig combining all sub-models`

---

## Task 5: Config 主模型 + WebDAV × library_type 兼容性矩阵

**Files:** Modify `src/zotero_cli/models/config.py` 和 `tests/unit/test_config_models.py`

`Config` 持有 `profiles: dict[str, ProfileConfig]`。`model_validator(mode="after")` 遍历每个 profile，按设计 §10.0.1 矩阵拒绝 `library_type=group + webdav 非空`，抛 `UnsupportedLibraryTypeError`（不是 `ConfigInvalidError`，因为这是业务语义而非 schema 错误，与 `config validate` 输出错误码一致）。

| library_type | webdav | 期望 |
|---|---|---|
| user | None | ✓ |
| user | 有 | ✓ |
| group | None | ✓ |
| group | 有 | ✗ `UnsupportedLibraryTypeError` |

**Key tests**:
```python
@pytest.mark.parametrize("library_type,has_webdav,ok", [
    ("user", False, True),
    ("user", True, True),
    ("group", False, True),
    ("group", True, False),
])
def test_compatibility_matrix(library_type, has_webdav, ok) -> None:
    profile_data = {"api_key": "k", "library_id": "1", "library_type": library_type}
    if has_webdav:
        profile_data["webdav"] = {"url": "https://x", "username": "u", "password": "p"}
    if ok:
        Config(profiles={"default": profile_data})
    else:
        with pytest.raises(UnsupportedLibraryTypeError) as ei:
            Config(profiles={"default": profile_data})
        assert "default" in (ei.value.context or {}).get("profile", "default")

def test_multiple_profiles() -> None:
    cfg = Config(profiles={
        "default": {"api_key": "k", "library_id": "1", "library_type": "user"},
        "work": {"api_key": "k2", "library_id": "2", "library_type": "group"},
    })
    assert set(cfg.profiles) == {"default", "work"}
```

**Implementation**:
```python
class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profiles: dict[str, ProfileConfig]

    @model_validator(mode="after")
    def _check_compat_matrix(self) -> "Config":
        for name, p in self.profiles.items():
            if p.library_type == "group" and p.webdav is not None:
                raise UnsupportedLibraryTypeError(
                    f"profile {name!r}: library_type='group' is incompatible with [webdav].",
                    hint="Zotero WebDAV sync does not support group libraries. "
                         "Remove [webdav] section or change library_type to 'user'.",
                    context={"profile": name, "library_type": "group"},
                )
        return self
```

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config): add Config with WebDAV × library_type compat matrix (design §10.0.1)`

---

## Task 6: 环境变量覆盖

**Files:** Modify `src/zotero_cli/services/config_service.py` 和 `tests/unit/test_config_service.py`

设计 §5.3：`ZOTERO_CLI_<PROFILE>_<KEY>` 覆盖任意配置项。由于 profile 名嵌入 prefix，pydantic-settings 标准 `env_nested_delimiter` 不直接适配。实现方式：先解析 TOML 拿到 `dict[profile, dict]`，再对目标 profile 的 dict 应用 env 覆盖（按下表静态映射），最后交给 `Config(profiles=...)` 校验。

**ENV_FIELD_MAP**（覆盖 §5.2 配置全集；嵌套字段路径用 tuple；list 字段从 env 取值时按 `,` 分隔）：

| Env suffix | 字段路径 |
|---|---|
| `API_KEY` / `LIBRARY_ID` / `LIBRARY_TYPE` | 顶层 |
| `WEBDAV_{URL,STORAGE_PATH,USERNAME,PASSWORD,TIMEOUT,VERIFY_SSL}` | `webdav.<f>` |
| `SQLITE_PATH` | `sqlite.path` |
| `ITEM_FIELDS_LIST` | `item_fields.list` |
| `FEED_ITEM_FIELDS_LIST` | `feed_item_fields.list` |

**Key tests**:
```python
def test_env_override_top_level(monkeypatch, tmp_path) -> None:
    write_toml(tmp_path / "config.toml", {"default": {
        "api_key": "from_file", "library_id": "1", "library_type": "user",
    }})
    monkeypatch.setenv("ZOTERO_CLI_DEFAULT_API_KEY", "from_env")
    cfg = load_config(profile="default", config_path=tmp_path / "config.toml")
    assert cfg.api_key == "from_env"

def test_env_override_webdav_password(monkeypatch, tmp_path) -> None:
    write_toml(tmp_path / "config.toml", {"work": {
        "api_key": "k", "library_id": "1", "library_type": "user",
        "webdav": {"url": "https://x", "username": "u", "password": "from_file"},
    }})
    monkeypatch.setenv("ZOTERO_CLI_WORK_WEBDAV_PASSWORD", "from_env")
    cfg = load_config(profile="work", config_path=tmp_path / "config.toml")
    assert cfg.webdav.password == "from_env"

def test_env_override_creates_webdav_section_if_missing(monkeypatch, tmp_path) -> None:
    # 注意：仅设 password 不够，url/username/password 三必填字段缺失会校验失败
    write_toml(tmp_path / "config.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    monkeypatch.setenv("ZOTERO_CLI_DEFAULT_WEBDAV_URL", "https://x")
    monkeypatch.setenv("ZOTERO_CLI_DEFAULT_WEBDAV_USERNAME", "u")
    monkeypatch.setenv("ZOTERO_CLI_DEFAULT_WEBDAV_PASSWORD", "p")
    cfg = load_config(profile="default", config_path=tmp_path / "config.toml")
    assert cfg.webdav.url == "https://x"

def test_env_override_list_field(monkeypatch, tmp_path) -> None:
    write_toml(tmp_path / "config.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    monkeypatch.setenv("ZOTERO_CLI_DEFAULT_ITEM_FIELDS_LIST", "key,title,date")
    cfg = load_config(profile="default", config_path=tmp_path / "config.toml")
    assert cfg.item_fields.list == ["key", "title", "date"]

def test_env_override_other_profile_ignored(monkeypatch, tmp_path) -> None:
    write_toml(tmp_path / "config.toml", {"default": {
        "api_key": "from_file", "library_id": "1", "library_type": "user",
    }})
    monkeypatch.setenv("ZOTERO_CLI_WORK_API_KEY", "should_not_apply")
    cfg = load_config(profile="default", config_path=tmp_path / "config.toml")
    assert cfg.api_key == "from_file"
```

**Implementation**: `_apply_env_overrides(profile_name: str, profile_dict: dict) -> dict` 静态映射 + nested 写入；`bool` 字段按 `"true"/"1"/"yes"` 解析；`int` 字段按 `int(...)` 解析；list 字段按 `","` 切分。详见设计 §5.3。`load_config` 完整流程见 Task 7。

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config_service): apply ZOTERO_CLI_<PROFILE>_<KEY> env overrides (design §5.3)`

---

## Task 6a: adapters/config_store.py — TOML 读写 + 路径检测

**Files:**
- Create: `src/zotero_cli/adapters/__init__.py`
- Create: `src/zotero_cli/adapters/config_store.py`
- Test: `tests/unit/test_config_store.py`

**作用范围**：唯一允许 import `tomllib` / `tomli_w` 并直接读写 `~/.config/zotero-cli/config.toml` 的层。后续 `services/config_service.py`、`commands/config.py` 全部走它。

**对外 API**：

```python
from typing import Any, TypeAlias

# 显式 alias：TOML 是 user-authored、半结构化文档，schema 由 pydantic-settings
# 在 service 层校验。adapter 不预先收紧 shape——所以保留 dict[str, Any]，
# 但用 alias 标注意图，让 reviewer 一眼看出"这是 boundary，不是被忽略"。
# 边界例外见 DEVELOPMENT.md §5.2。
RawTomlDocument: TypeAlias = dict[str, Any]


def read_toml(path: Path) -> RawTomlDocument: ...
def write_toml(path: Path, data: RawTomlDocument) -> None: ...   # 创建父目录 + chmod 0600
def default_config_path() -> Path: ...                            # ~/.config/zotero-cli/config.toml（XDG 兼容）
def detect_sqlite_db(env_override: str | None = None) -> str | None: ...  # 设计 §5.4 三段查找
```

> **回应 review P2 Issue 3（公开返回裸 dict）**：DEVELOPMENT.md §4.2 禁止裸 `dict[str, Any]` 公开返回，但 §5.2 已为 adapter 边界注明例外（"外部数据透传"——TOML 文档、Zotero API item dicts、pyzotero 批量返回）。本任务用显式 `RawTomlDocument` TypeAlias 替代裸 `dict[str, Any]`，并把 alias 定义在 adapter 模块顶部（无第三方依赖，纯类型注解）。pydantic-settings 在 `models/config.py` 收紧到 `Config` 强类型。同样的 alias 模式也用于 Phase 4 的 pyzotero 透传层（见那边）。

**Key tests**：

```python
import os
import stat
from pathlib import Path

import pytest
from zotero_cli.adapters.config_store import (
    read_toml, write_toml, default_config_path, detect_sqlite_db,
)
from zotero_cli.models.errors import ConfigInvalidError, ConfigNotFoundError


def test_read_toml_missing_raises_config_not_found(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError):
        read_toml(tmp_path / "nope.toml")


def test_read_toml_invalid_syntax_raises_config_invalid(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text("not = valid = toml")
    with pytest.raises(ConfigInvalidError):
        read_toml(p)


def test_write_toml_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    write_toml(p, {"default": {"api_key": "k", "library_id": "1"}})
    assert read_toml(p) == {"default": {"api_key": "k", "library_id": "1"}}


def test_write_toml_sets_0600(tmp_path: Path) -> None:
    p = tmp_path / "c.toml"
    write_toml(p, {"x": {"y": 1}})
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600


def test_write_toml_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "subdir" / "c.toml"
    write_toml(p, {"x": {"y": 1}})
    assert p.exists()


def test_default_config_path_uses_xdg_or_home() -> None:
    # 只验证形式：应以 zotero-cli/config.toml 结尾
    assert default_config_path().name == "config.toml"
    assert default_config_path().parent.name == "zotero-cli"


def test_detect_sqlite_db_env_override(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "zotero.sqlite").touch()
    monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
    assert detect_sqlite_db() == str(tmp_path / "zotero.sqlite")


def test_detect_sqlite_db_explicit_arg_wins(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "zotero.sqlite").touch()
    other = tmp_path / "other"
    other.mkdir()
    (other / "zotero.sqlite").touch()
    monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
    assert detect_sqlite_db(env_override=str(other)) == str(other / "zotero.sqlite")


def test_detect_sqlite_db_none_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # 平台默认 fallback 也不存在
    assert detect_sqlite_db() is None
```

**Implementation skeleton**：

```python
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

# 显式 alias：见上方"对外 API"段的说明（adapter boundary）。
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
    path.chmod(0o600)  # 设计 §5.1


def detect_sqlite_db(env_override: str | None = None) -> str | None:
    """Find zotero.sqlite per design §5.4 priority:
    1. env_override (caller-supplied; usually from ZOTERO_DATA_DIR or config explicit path's parent)
    2. ZOTERO_DATA_DIR env var
    3. Platform defaults (Linux/macOS ~/Zotero, Windows %USERPROFILE%\\Zotero, Snap, Flatpak)
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
        candidates.append(home / ".var" / "app" / "org.zotero.Zotero" / "data" / "Zotero" / "zotero.sqlite")
    for p in candidates:
        if p.exists():
            return str(p)
    return None
```

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config_store): add TOML read/write + 0600 + sqlite path detection (design §5.1, §5.4)`

---

## Task 6b: commands/_runner.py — GlobalOptions + run_command + emit_failure

**Files:**
- Create: `src/zotero_cli/commands/_runner.py`
- Test: `tests/unit/test_command_runner.py`

> **回应 review P1 Issue 1（utils 分层）**：runner 放在 `commands/`，不在 `utils/`。原因：runner 调 `sys.exit` 并写 stdout/stderr，是 CLI 命令路径的最薄包装，符合 DEVELOPMENT.md §5.2 修订后的"`commands/` 允许 sys.exit 与写流"。文件名前缀 `_` 表示模块内部基础设施（不是 typer subcommand）。
>
> **回应 review P1 Issue 2 + 3**：所有命令模块共享：
> 1. `GlobalOptions` dataclass（属性访问，避免 ctx.obj["..."] / ctx.obj.x 不一致）
> 2. `run_command(...)` runner：mutex 校验 + 定时 + try/except CLIError + render → 按设计 §7.5 写正确的 stream → 调 `sys.exit(err.exit_code)`
> 3. `emit_failure(...)` **公开** helper（无下划线前缀）：直接给 envelope failure 渲染 + 写流，给 export 这种"不走标准 envelope"的特殊命令复用

**对外 API**：

```python
@dataclass
class GlobalOptions:
    profile: str = "default"
    json_mode: bool = False
    quiet: bool = False
    config_path: Path | None = None  # 测试场景注入；None = 走 default_config_path()


def run_command(
    *,
    command: str,                 # envelope MetaObject.command（如 "items.list" / "schema"）
    mode: OutputMode,
    options: GlobalOptions,
    work: Callable[[], Any],      # service 调用闭包：返回 envelope.data 用的 dict / list / None
    meta_extra: dict[str, Any] | None = None,
    field_filter: list[str] | None = None,
) -> NoReturn:
    """Pre-validate → call work() → render → write to correct stream → sys.exit.

    Pre-validation (before work()):
      - --json + --quiet → MUTUALLY_EXCLUSIVE_ARGS, exit 64.
      - --quiet + mode in {YAML, JSON} → MUTUALLY_EXCLUSIVE_ARGS, exit 64
        (设计 §7.2 表：YAML / JSON 模式不接受 --quiet).

    Run-time:
      - work() raises CLIError → envelope.failure, route per options.
      - render() raises CLIError → envelope.failure, route per options
        (defense-in-depth for any future render-side validation).

    Routing (设计 §7.5):
      - Success → stdout, exit 0.
      - Default mode error → stderr, exit err.exit_code.
      - --json mode error → stdout (still valid envelope JSON), exit err.exit_code.
    """
```

**Key tests**（用 capsys 验证流向）：

```python
import sys
from dataclasses import dataclass
import pytest

from zotero_cli.commands._runner import GlobalOptions, run_command, emit_failure
from zotero_cli.utils.output import OutputMode
from zotero_cli.models.errors import ItemNotFoundError


def test_success_writes_to_stdout(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(),
            work=lambda: {"key": "ABC", "title": "T"},
        )
    assert ei.value.code == 0
    cap = capsys.readouterr()
    assert "key: ABC" in cap.out
    assert cap.err == ""


def test_default_mode_error_writes_to_stderr(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(json_mode=False),
            work=lambda: (_ for _ in ()).throw(ItemNotFoundError("nope")),
        )
    assert ei.value.code == 1
    cap = capsys.readouterr()
    assert cap.out == ""  # 设计 §7.5：默认模式 stdout 为空
    assert "ITEM_NOT_FOUND" in cap.err


def test_json_mode_error_writes_envelope_to_stdout(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(json_mode=True),
            work=lambda: (_ for _ in ()).throw(ItemNotFoundError("nope")),
        )
    assert ei.value.code == 1
    cap = capsys.readouterr()
    assert cap.err == ""  # --json 模式：错误也走 stdout
    import json
    parsed = json.loads(cap.out)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "ITEM_NOT_FOUND"


def test_quiet_and_json_mutex_raises(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show",
            mode=OutputMode.KV,
            options=GlobalOptions(json_mode=True, quiet=True),
            work=lambda: {"key": "ABC"},
        )
    assert ei.value.code == 64  # MUTUALLY_EXCLUSIVE_ARGS


def test_meta_extra_propagates(capsys) -> None:
    with pytest.raises(SystemExit):
        run_command(
            command="items.list", mode=OutputMode.KV_LIST,
            options=GlobalOptions(json_mode=True),
            work=lambda: [{"key": "X"}],
            meta_extra={"count": 1, "library_id": "12345"},
        )
    import json
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["meta"]["count"] == 1
    assert parsed["meta"]["library_id"] == "12345"
```

**Implementation skeleton**：

```python
"""commands/_runner.py — shared CLI command runner (commands-layer infra).

Per DEVELOPMENT.md §5.2: this module is allowed to call sys.exit and write
stdout/stderr because it serves the CLI command path. utils/ is not.
GlobalOptions (ctx.obj 契约) + run_command (timing, error capture,
stdout/stderr split per design §7.5).
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NoReturn

from zotero_cli.models.envelope import Envelope
from zotero_cli.models.errors import CLIError, MutuallyExclusiveArgsError
# render() is imported as a module attribute (not 'from ... import render') so
# tests can monkeypatch zotero_cli.commands._runner._output.render without re-import.
from zotero_cli.utils import output as _output  # noqa: PLR0402


@dataclass
class GlobalOptions:
    profile: str = "default"
    json_mode: bool = False
    quiet: bool = False
    config_path: Path | None = None


def run_command(
    *,
    command: str,
    mode: "_output.OutputMode",
    options: GlobalOptions,
    work: Callable[[], Any],
    meta_extra: dict[str, Any] | None = None,
    field_filter: list[str] | None = None,
) -> NoReturn:
    # 1) 全局 mutex（设计 §7.2）
    if options.json_mode and options.quiet:
        err = MutuallyExclusiveArgsError(
            "--json and --quiet cannot be combined",
            hint="Use --json for full envelope, --quiet for affected_keys only.",
        )
        emit_failure(err, command, 0, options)
        sys.exit(err.exit_code)

    # 2) Mode-specific quiet 不支持检查（设计 §7.2 表）
    if options.quiet and mode in (_output.OutputMode.YAML, _output.OutputMode.JSON):
        err = MutuallyExclusiveArgsError(
            f"--quiet is not supported for {mode.value} output",
            hint="Use --json for machine-readable output instead.",
        )
        emit_failure(err, command, 0, options)
        sys.exit(err.exit_code)

    # 3) 调 service
    start = time.perf_counter()
    try:
        data = work()
    except CLIError as err:
        elapsed = int((time.perf_counter() - start) * 1000)
        emit_failure(err, command, elapsed, options)
        sys.exit(err.exit_code)

    elapsed = int((time.perf_counter() - start) * 1000)

    # 4) 渲染——render() 也可能 raise CLIError（render-side validation 失败），
    #    一并捕获走 envelope failure 路径。
    try:
        env = Envelope.success(
            data=data, command=command, elapsed_ms=elapsed, meta_extra=meta_extra,
        )
        out = _output.render(
            envelope=env, mode=mode,
            json_mode=options.json_mode, quiet=options.quiet,
            field_filter=field_filter,
        )
    except CLIError as err:
        emit_failure(err, command, elapsed, options)
        sys.exit(err.exit_code)

    if out:
        sys.stdout.write(out)
    sys.exit(0)


def emit_failure(
    err: CLIError, command: str, elapsed_ms: int, options: GlobalOptions,
) -> None:
    """Public helper: render an envelope failure and write to the right stream.

    Used by run_command and by special command paths (e.g. items export) that
    don't go through run_command but still need design §7.5 stdout/stderr split.

    Caller is responsible for calling sys.exit(err.exit_code) afterward.

    Defense-in-depth: if `_output.render` itself raises (very rare — the
    failure-path render uses a fully-validated Envelope that doesn't depend on
    user data), fall back to a hand-built minimal envelope. Per design §7.5,
    --json mode stdout is ALWAYS valid JSON, including on errors. So:

      - json_mode=True  → write a hand-rolled minimal JSON envelope to stdout.
      - json_mode=False → write a one-line "✗ Error: CODE\n  MSG\n" to stderr.
    """
    try:
        env = Envelope.failure(err, command=command, elapsed_ms=elapsed_ms)
        out = _output.render(
            envelope=env, mode=_output.OutputMode.KV,
            json_mode=options.json_mode, quiet=False,
        )
    except Exception:  # pragma: no cover — defense in depth
        if options.json_mode:
            # 设计 §7.5 invariant：json mode stdout 永远是合法 JSON envelope。
            # 兜底版本只用 err 的核心字段，不依赖 pydantic 序列化（万一 pydantic 也炸了）。
            import json as _json
            payload = {
                "ok": False,
                "data": None,
                "error": {
                    "code": err.code,
                    "message": err.message,
                    "category": err.category,
                    "hint": err.hint,
                    "context": err.context if err.context else None,
                    "cause": None,
                },
                "meta": {
                    "command": command,
                    "elapsed_ms": elapsed_ms,
                    "exit_code": err.exit_code,
                },
            }
            sys.stdout.write(_json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            sys.stderr.write(f"✗ Error: {err.code}\n  {err.message}\n")
        return
    stream = sys.stdout if options.json_mode else sys.stderr
    stream.write(out)
```

> **设计要点 1**：`output` 用 `import zotero_cli.utils.output as _output` 而不是 `from ... import render`——这样测试可以 `mocker.patch("zotero_cli.commands._runner._output.render", ...)` 生效（直接 `from` 形式会留下本地 binding）。
>
> **设计要点 2**：`emit_failure` 是公开 API（无下划线前缀），给 `commands/items.py` 的 export 命令复用。任何"不走 run_command"的命令都应该 import 它，避免重复实现 stdout/stderr 分离规则。
>
> **设计要点 3（回应 review P2 Issue 5）**：`emit_failure` 兜底分支必须保持设计 §7.5 的 stdout/stderr 契约：
> - `json_mode=True` → 即使 render 自己崩溃，也要在 stdout 写一个**手工 dump 的最小 JSON envelope**（不经过 pydantic，避免二次崩溃）。这样 agent / `jq` 解析端永远不会读到非 JSON 的 stdout。
> - `json_mode=False` → 写一行纯文本到 stderr。
>
> 这两条都不"沉默退出"——每一条错误路径都会留下 trace。

**关键测试**（新增覆盖 yaml + quiet 拦截）：

```python
def test_yaml_mode_with_quiet_rejected_before_work(capsys, mocker) -> None:
    """run_command 必须在调 work() 前拒绝 yaml + quiet（设计 §7.2 表）"""
    work_spy = mocker.Mock()
    with pytest.raises(SystemExit) as ei:
        run_command(
            command="config.show",
            mode=OutputMode.YAML,
            options=GlobalOptions(quiet=True),
            work=work_spy,
        )
    assert ei.value.code == 64  # MUTUALLY_EXCLUSIVE_ARGS
    work_spy.assert_not_called()  # 关键：work 完全不应被调
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "MUTUALLY_EXCLUSIVE_ARGS" in cap.err


def test_render_raised_cli_error_handled_as_envelope_failure(
    capsys, mocker,
) -> None:
    """如果 render() 自己抛 CLIError（render-side validation 失败），
    runner 走 envelope failure 路径，不让异常逃逸到 typer。

    注：runner 用 `import zotero_cli.utils.output as _output` 引入 render，
    所以 patch 路径是 `zotero_cli.commands._runner._output.render`（实现要点 1）。
    我们让 success-path render 抛错，但 emit_failure 内部的 render 调用
    返回正常值——因此用 side_effect 列表：第一次抛 CLIError，第二次正常返回 fallback 字符串。"""
    from zotero_cli.models.errors import ConfigInvalidError

    def fake_render_seq(**kwargs):
        # 第一次（success-path）→ 抛错；
        # 第二次（emit_failure 渲染失败 envelope）→ 返回正常字符串
        if not getattr(fake_render_seq, "called", False):
            fake_render_seq.called = True
            raise ConfigInvalidError("bad shape for kv (test)")
        return "✗ Error: CONFIG_INVALID\n  bad shape for kv (test)\n"

    mocker.patch(
        "zotero_cli.commands._runner._output.render",
        side_effect=fake_render_seq,
    )

    with pytest.raises(SystemExit) as ei:
        run_command(
            command="x.y", mode=OutputMode.KV,
            options=GlobalOptions(),
            work=lambda: {"key": "ABC"},
        )
    assert ei.value.code == 4  # local_error
    cap = capsys.readouterr()
    assert "CONFIG_INVALID" in cap.err
    assert cap.out == ""


def test_emit_failure_render_crash_default_mode_writes_plaintext_to_stderr(
    capsys, mocker,
) -> None:
    """defense-in-depth (默认模式): emit_failure 自己的 render 抛非 CLIError 异常时，
    落到一行 plain-text stderr，stdout 空。"""
    mocker.patch(
        "zotero_cli.commands._runner._output.render",
        side_effect=RuntimeError("render is totally broken"),
    )
    from zotero_cli.models.errors import ItemNotFoundError

    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show", mode=OutputMode.KV,
            options=GlobalOptions(json_mode=False),
            work=lambda: (_ for _ in ()).throw(ItemNotFoundError("nope")),
        )
    assert ei.value.code == 1  # ItemNotFoundError category=user_error → exit 1
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "✗ Error: ITEM_NOT_FOUND" in cap.err
    assert "nope" in cap.err


def test_emit_failure_render_crash_json_mode_writes_envelope_to_stdout(
    capsys, mocker,
) -> None:
    """defense-in-depth (json_mode): emit_failure 兜底也必须保持设计 §7.5 invariant —
    json mode stdout 是合法 JSON envelope，stderr 空。"""
    mocker.patch(
        "zotero_cli.commands._runner._output.render",
        side_effect=RuntimeError("render is totally broken"),
    )
    from zotero_cli.models.errors import ItemNotFoundError

    with pytest.raises(SystemExit) as ei:
        run_command(
            command="items.show", mode=OutputMode.KV,
            options=GlobalOptions(json_mode=True),
            work=lambda: (_ for _ in ()).throw(
                ItemNotFoundError("nope", hint="try items list")
            ),
        )
    assert ei.value.code == 1
    cap = capsys.readouterr()
    assert cap.err == ""  # 兜底也不准漏到 stderr
    import json as _json
    parsed = _json.loads(cap.out)  # 必须能 parse
    assert parsed["ok"] is False
    assert parsed["data"] is None
    assert parsed["error"]["code"] == "ITEM_NOT_FOUND"
    assert parsed["error"]["message"] == "nope"
    assert parsed["error"]["hint"] == "try items list"
    assert parsed["error"]["category"] == "user_error"
    assert parsed["meta"]["command"] == "items.show"
    assert parsed["meta"]["exit_code"] == 1
```

> **回应 review P2 Issue 5**：① 测试函数现已包含 `mocker` fixture（pytest-mock）；② patch 路径改成 `zotero_cli.commands._runner._output.render`，与实现的 `import ... as _output` 形式匹配；③ 用 `side_effect` 序列让"success-path render 抛 / failure-path render 正常"，避免重入死循环；④ 加第二个测试覆盖"failure-path render 也抛"的兜底分支。

**Steps**：写测试 → 失败 → 实现（`commands/_runner.py`，遵循 DEVELOPMENT.md §5.2 修订）→ 通过 → ruff + mypy → commit `feat(commands/_runner): GlobalOptions + run_command + emit_failure (stdout/stderr split per design §7.5)`

---

## Task 7: load_config + validate_profile 编排

**Files:** Modify `src/zotero_cli/services/config_service.py` 和 `tests/unit/test_config_service.py`

`load_config(profile, *, config_path=None) -> ProfileConfig`：组装顺序固定 = 读 TOML → 应用 env 覆盖 → SQLite path 自动检测兜底 → 构造 `Config(profiles={profile: dict})` 触发兼容性矩阵 → 取出对应 `ProfileConfig` 返回。`validate_profile(profile, *, config_path=None) -> None`：调 `load_config` 即足够（pydantic 校验 + 矩阵都已触发），仅作为 commands 层的稳定入口。`config_path=None` 时走默认 `~/.config/zotero-cli/config.toml`（XDG）。

**Key tests**:
```python
def test_load_config_missing_file_raises_config_not_found(tmp_path) -> None:
    with pytest.raises(ConfigNotFoundError):
        load_config(profile="default", config_path=tmp_path / "nope.toml")

def test_load_config_unknown_profile_raises_invalid_profile(tmp_path) -> None:
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    with pytest.raises(InvalidProfileError) as ei:
        load_config(profile="missing", config_path=tmp_path / "c.toml")
    assert "available" in (ei.value.hint or "").lower()

def test_load_config_invalid_toml_syntax(tmp_path) -> None:
    (tmp_path / "c.toml").write_text("not = valid = toml")
    with pytest.raises(ConfigInvalidError):
        load_config(profile="default", config_path=tmp_path / "c.toml")

def test_load_config_sqlite_autodetect_filled_in(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ZOTERO_DATA_DIR", str(tmp_path))
    (tmp_path / "zotero.sqlite").touch()
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    cfg = load_config(profile="default", config_path=tmp_path / "c.toml")
    assert cfg.sqlite.path == str(tmp_path / "zotero.sqlite")

def test_validate_profile_passes_silently(tmp_path) -> None:
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    validate_profile(profile="default", config_path=tmp_path / "c.toml")  # no raise

def test_validate_profile_group_with_webdav_raises(tmp_path) -> None:
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "group",
        "webdav": {"url": "https://x", "username": "u", "password": "p"},
    }})
    with pytest.raises(UnsupportedLibraryTypeError):
        validate_profile(profile="default", config_path=tmp_path / "c.toml")
```

**Implementation** sketch（I/O 全部委托给 `adapters/config_store`；本模块只编排）：
```python
from zotero_cli.adapters.config_store import (
    read_toml, default_config_path, detect_sqlite_db,
)
from zotero_cli.models.config import Config, ProfileConfig
from zotero_cli.models.errors import ConfigInvalidError, InvalidProfileError, UnsupportedLibraryTypeError


def load_config(profile: str, *, config_path: Path | None = None) -> ProfileConfig:
    path = config_path or default_config_path()
    raw = read_toml(path)  # 抛 ConfigNotFoundError / ConfigInvalidError，不在本层处理
    if profile not in raw:
        raise InvalidProfileError(
            f"Profile {profile!r} not found in {path}",
            hint=f"Available profiles: {', '.join(sorted(raw)) or '(none)'}",
        )
    profile_dict = _apply_env_overrides(profile, dict(raw[profile]))
    profile_dict = _fill_sqlite_default(profile_dict)  # 内部只调 detect_sqlite_db()
    cfg = Config(profiles={profile: profile_dict})  # pydantic 触发兼容性矩阵
    return cfg.profiles[profile]


def validate_profile(profile: str, *, config_path: Path | None = None) -> None:
    load_config(profile=profile, config_path=config_path)


def _fill_sqlite_default(profile_dict: dict) -> dict:
    sqlite = profile_dict.get("sqlite", {})
    if sqlite.get("path"):
        return profile_dict
    detected = detect_sqlite_db()
    if detected:
        profile_dict = dict(profile_dict)
        profile_dict.setdefault("sqlite", {})["path"] = detected
    return profile_dict
```

> **架构纪律**（DEVELOPMENT.md §5.2）：本模块不允许 import `tomllib` / `tomli_w` / `Path.exists` / `Path.read_text` / `Path.write_text`。任何 I/O 都通过 `adapters/config_store`。Test 时也不直接读写文件——`read_toml` 由 `adapters` 单测覆盖，`config_service` 测试用 mock 或经过 adapter（更接近真实路径）。

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(config_service): add load_config + validate_profile orchestration (no direct I/O)`

---

## Task 8: commands/config.py — init + show

**Files:**
- Create: `src/zotero_cli/commands/__init__.py`（空）
- Create: `src/zotero_cli/commands/config.py`
- Create: `src/zotero_cli/cli.py`（仅占位 + 注册 `config` sub-app；阶段 6 完整化）
- Test: `tests/unit/test_config_commands.py`

`config init`：调 `adapters/config_store.write_toml(path, default_profile_data)`（自动 0600）；文件已存在则 `--force` 才覆盖。`config show [--profile NAME]`：调 `services/config_service.load_config(profile)` 拿 `ProfileConfig`，组成 dict 后通过 `commands._runner.run_command(...)` 渲染为 yaml。**所有命令通过 `run_command` 走错误捕获 + stdout/stderr 分离**——本模块自己**不写** try/except CLIError，更不直接写 stderr。

> **回应 review P1 Issue 1 + 3**：`config init` 不再 import `tomli_w` / 不调 `os.chmod`。所有 I/O 经过 `adapters/config_store`；所有命令的输出经过 `commands._runner.run_command`。

**Key tests** (Typer's `CliRunner`):
```python
def test_init_creates_file_with_0600_perm(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path",
        lambda: tmp_path / "c.toml",
    )
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "c.toml").exists()
    assert oct((tmp_path / "c.toml").stat().st_mode & 0o777) == "0o600"

def test_init_refuses_overwrite_without_force(tmp_path, monkeypatch) -> None:
    from zotero_cli.adapters.config_store import write_toml
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path",
        lambda: tmp_path / "c.toml",
    )
    write_toml(tmp_path / "c.toml", {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}})
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    # stderr 检查：默认模式错误走 stderr
    assert "exists" in result.stderr.lower() or "already" in result.stderr.lower()

def test_show_yaml_default_with_masked_secrets(tmp_path, monkeypatch) -> None:
    from zotero_cli.adapters.config_store import write_toml
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path",
        lambda: tmp_path / "c.toml",
    )
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "secretkey1234", "library_id": "1", "library_type": "user",
    }})
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 0
    assert "secr****" in result.stdout
    assert "secretkey1234" not in result.stdout
    assert result.stderr == ""

def test_show_json_emits_full_envelope(tmp_path, monkeypatch) -> None:
    from zotero_cli.adapters.config_store import write_toml
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path",
        lambda: tmp_path / "c.toml",
    )
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    result = runner.invoke(app, ["--json", "show"])
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is True
    assert parsed["data"]["library_id"] == "1"
    assert result.stderr == ""

def test_show_unknown_profile_default_mode_writes_stderr(tmp_path, monkeypatch) -> None:
    from zotero_cli.adapters.config_store import write_toml
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path",
        lambda: tmp_path / "c.toml",
    )
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    result = runner.invoke(app, ["show", "--profile", "missing"])
    assert result.exit_code == 1
    assert result.stdout == ""  # 设计 §7.5：默认模式 stdout 空
    assert "INVALID_PROFILE" in result.stderr

def test_show_unknown_profile_json_mode_writes_stdout(tmp_path, monkeypatch) -> None:
    from zotero_cli.adapters.config_store import write_toml
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path",
        lambda: tmp_path / "c.toml",
    )
    write_toml(tmp_path / "c.toml", {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
    }})
    result = runner.invoke(app, ["--json", "show", "--profile", "missing"])
    assert result.exit_code == 1
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "INVALID_PROFILE"
    assert result.stderr == ""
```

**Implementation pointers**:
- `app = typer.Typer(help="Manage zotero-cli config")`，全局 flag (`--json`、`--profile`、`--quiet`) 在 `cli.py` 顶层 callback 声明，构造 `GlobalOptions` 并 `ctx.obj = options`。子命令通过 `ctx.obj` 取
- 子命令通过 `run_command(command="config.init", mode=OutputMode.SUMMARY, options=ctx.obj, work=lambda: ...)` 调用：work 函数返回 envelope.data，runner 负责其余
- `init` 的 work：检查 `path.exists()`（通过 `adapters/config_store` 暴露的 `path_exists` helper 或直接接受 `FileExistsError` → 翻译为 `ConfigInvalidError("config exists; use --force")`）；`config_store.write_toml(path, template)` 完成
- `show` 的 work：`load_config(profile=options.profile, config_path=options.config_path)` → 返回 dict 含 `profile` + 各字段
- 错误处理**完全交给 run_command**，本模块绝不自己 catch CLIError 或 sys.exit
- 0600 权限由 `config_store.write_toml` 保证（DEVELOPMENT.md §10.1）

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(commands/config): add init and show via run_command + config_store`

---

## Task 9: commands/config.py — set + get

**Files:** Modify `src/zotero_cli/commands/config.py` 和 `tests/unit/test_config_commands.py`

`config set <key> <value> [--profile NAME]`：`<key>` 用点路径（`api_key` / `webdav.password` / `item_fields.list`）；list 字段 CLI 端按 `,` 切分。**所有 I/O 走 `adapters/config_store`**：`read_toml` → 修改 profile dict → 跑一次 `Config(profiles=...)` 校验 → `write_toml`（自动 0600）。`config get <key> [--profile NAME]`：`load_config` → 按点路径取值 → 渲染 KV。敏感字段（`api_key` / `webdav.password`）默认掩码。

> **回应 review P1 Issue 1 + 3**：本任务不直接 import `tomllib` / `tomli_w` / `os.chmod`；所有命令通过 `commands._runner.run_command(...)` 执行，错误捕获/stream 分离都委托给 runner。

**Key tests**（用 monkeypatch 把 default_config_path 指向 tmp_path）:
```python
@pytest.fixture
def cfg_at(monkeypatch, tmp_path):
    """Helper: redirects default_config_path to tmp_path/c.toml."""
    p = tmp_path / "c.toml"
    monkeypatch.setattr(
        "zotero_cli.adapters.config_store.default_config_path", lambda: p,
    )
    return p

def test_set_top_level_writes_back(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml, read_toml
    write_toml(cfg_at, {"default": {"api_key": "old", "library_id": "1", "library_type": "user"}})
    result = runner.invoke(app, ["set", "api_key", "new"])
    assert result.exit_code == 0
    assert read_toml(cfg_at)["default"]["api_key"] == "new"
    assert oct(cfg_at.stat().st_mode & 0o777) == "0o600"  # write_toml 兜底了 0600

def test_set_nested_webdav_password(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml, read_toml
    write_toml(cfg_at, {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
        "webdav": {"url": "https://x", "username": "u", "password": "old"},
    }})
    runner.invoke(app, ["set", "webdav.password", "new"])
    assert read_toml(cfg_at)["default"]["webdav"]["password"] == "new"

def test_set_breaks_compat_matrix_rejected(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg_at, {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
        "webdav": {"url": "https://x", "username": "u", "password": "p"},
    }})
    result = runner.invoke(app, ["set", "library_type", "group"])
    assert result.exit_code == 1
    assert result.stdout == ""  # 默认模式
    assert "UNSUPPORTED_LIBRARY_TYPE" in result.stderr

def test_set_list_field_from_csv(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml, read_toml
    write_toml(cfg_at, {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}})
    runner.invoke(app, ["set", "item_fields.list", "key,title,date"])
    assert read_toml(cfg_at)["default"]["item_fields"]["list"] == ["key", "title", "date"]

def test_get_returns_value(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg_at, {"default": {"api_key": "k", "library_id": "12345", "library_type": "user"}})
    result = runner.invoke(app, ["get", "library_id"])
    assert result.exit_code == 0
    assert "value: 12345" in result.stdout

def test_get_password_masked(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg_at, {"default": {
        "api_key": "k", "library_id": "1", "library_type": "user",
        "webdav": {"url": "https://x", "username": "u", "password": "secret"},
    }})
    result = runner.invoke(app, ["get", "webdav.password"])
    assert "secret" not in result.stdout
    assert "****" in result.stdout

def test_get_unknown_key_invalid_field(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg_at, {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}})
    result = runner.invoke(app, ["get", "nonexistent"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "INVALID_FIELD" in result.stderr
```

**Implementation pointers**:
- 点路径解析：`"webdav.password".split(".")` → 嵌套字典 set/get；list 字段在 set 端做 `value.split(",")`
- set 流程：`config_store.read_toml(path)` → 修改 dict → `Config(profiles={...})` 校验（含矩阵）→ `config_store.write_toml(path, raw)`（自动 0600）。校验失败的 CLIError 直接透传给 `run_command`
- get 用本地小集合维护敏感键（不跨 `utils/output` 层），保持各层职责单一
- 都不写 audit log（设计 §9.4 仅记录服务端写操作）
- 错误处理一律走 `run_command`

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(commands/config): add set and get via run_command + config_store with matrix re-validation`

---

## Task 10: commands/config.py — validate + profiles

**Files:** Modify `src/zotero_cli/commands/config.py` 和 `tests/unit/test_config_commands.py`

`config validate [--profile NAME]`：调 `services/config_service.validate_profile()`；通过则返回 `{"profile": name, "valid": True}`，失败让 `CLIError` 透传到 `run_command`。`config profiles`：调 `adapters/config_store.read_toml(path)` 拿原始 dict 后取 keys（不走 `load_config`，确保 schema 错误时也能列出 profiles）。

> 同样**所有 I/O 走 adapters，所有错误处理走 run_command**，本模块不直接 import `tomllib`。

**Key tests**:
```python
def test_validate_passes(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg_at, {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}})
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert "valid" in result.stdout.lower()

def test_validate_group_with_webdav_fails(cfg_at) -> None:
    from zotero_cli.adapters.config_store import write_toml
    write_toml(cfg_at, {"default": {
        "api_key": "k", "library_id": "1", "library_type": "group",
        "webdav": {"url": "https://x", "username": "u", "password": "p"},
    }})
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "UNSUPPORTED_LIBRARY_TYPE" in result.stderr

def test_validate_storage_path_normalize_failure(cfg_at) -> None:
    cfg_at.write_text(
        '[default]\napi_key="k"\nlibrary_id="1"\nlibrary_type="user"\n'
        '[default.webdav]\nurl="https://x"\nusername="u"\npassword="p"\n'
        'storage_path="//bad"\n'
    )
    cfg_at.chmod(0o600)
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "CONFIG_INVALID" in result.stderr or "storage_path" in result.stderr

def test_profiles_lists_all(tmp_path, monkeypatch) -> None:
    write_toml(tmp_path / "c.toml", {
        "default": {"api_key": "k", "library_id": "1", "library_type": "user"},
        "work": {"api_key": "k", "library_id": "2", "library_type": "user"},
    })
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "c.toml")
    result = runner.invoke(app, ["profiles"])
    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "work" in result.stdout

def test_profiles_quiet_outputs_names(tmp_path, monkeypatch) -> None:
    write_toml(tmp_path / "c.toml", {
        "default": {"api_key": "k", "library_id": "1", "library_type": "user"},
        "work": {"api_key": "k", "library_id": "2", "library_type": "user"},
    })
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", tmp_path / "c.toml")
    result = runner.invoke(app, ["--quiet", "profiles"])
    # --quiet 列表模式取每项的 key 字段；profiles 命令用 name → 临时映射 name=key
    # 预期输出：每行一个 profile 名
    assert sorted(result.stdout.strip().split("\n")) == ["default", "work"]
```

**Implementation pointers**:
- `profiles` 输出 list[dict]，每项含 `key`（profile 名，对齐 `--quiet` 取 `key` 字段的约定）和 `name`；KV_LIST 模式默认显示 `key:` 和 `name:` 两行
- `validate` 通过时输出最简对象（`profile`、`valid: true`），mode 用 KV
- 全局 flag `--profile`、`--json`、`--quiet` 由 `cli.py` 顶层声明、`Context.obj` 透传，每个子命令实际从 ctx 读

**Steps**：写测试 → 失败 → 实现 → 通过 → ruff + mypy → commit `feat(commands/config): add validate and profiles subcommands`

---

## Task 11: 阶段 2 整体覆盖率验证 + DEVELOPMENT.md §9.2 勾选

**Files:** `DEVELOPMENT.md`（如更新）

- [ ] **Step 1**：跑完整自检（DEVELOPMENT.md §6.6）

  ```bash
  uv run ruff check src tests
  uv run ruff format --check src tests
  uv run mypy src
  uv run pytest --cov=src/zotero_cli --cov-report=term-missing
  ```

- [ ] **Step 2**：核对覆盖率（设计 §12.4 / DEVELOPMENT.md §9.2）

  | 模块 | 目标 | 实测 |
  |---|---|---|
  | `models/config.py` | 95%+ | ____ |
  | `adapters/config_store.py` | 95%+ | ____ |
  | `services/config_service.py` | 85%+ | ____ |
  | `commands/_runner.py` | 95%+ | ____ |
  | `commands/config.py` | 70%+ | ____ |

  未达标 → 补测试 → 重跑。

- [ ] **Step 3**：勾选 `DEVELOPMENT.md §9.2` 中阶段 2 的所有 `[ ]` → `[x]`。

- [ ] **Step 4**：commit

  ```bash
  git add DEVELOPMENT.md
  git commit -m "docs: tick phase 2 acceptance checklist"
  ```

阶段 2 完成。下一步进入阶段 3（pyzotero spike + Zotero API 适配），按设计 §13 阶段 3 顺序，先做 spike 再实施。

---

## 自检清单（每个 Task 都要满足）

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src/zotero_cli --cov-report=term-missing
```

四项全过才能 commit。每次 commit 前确认：

- 当前 task 的所有测试 pass
- 不引入新的 mypy strict error / ruff finding
- 没误把 `~/.config/zotero-cli/config.toml` 这类本地真实配置入库（用 `git status` 复核）
- 没在测试里写真实 API key / WebDAV 密码（DEVELOPMENT.md §10.3）

---

## 阶段验收 checklist

参见 `DEVELOPMENT.md §9.2`。Task 11 负责把所有 `[ ]` 勾选完。
