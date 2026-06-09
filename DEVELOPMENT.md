# DEVELOPMENT.md — zotero-cli 协作运行手册

**适用版本**：与 `docs/superpowers/specs/2026-06-07-zotero-cli-design.md` 同步
**最后更新**：2026-06-07
**读者**：所有参与 zotero-cli 实施的 agent

---

## §1. 文档定位与读者

本文是给**实施 agent** 读的协作运行手册。它不重复设计文档，而是把"该怎么协作、该怎么写代码、该怎么验收"这些可执行规则集中在一起。

**优先级（冲突时由高到低）**：

1. 项目根目录 `CLAUDE.md`（用户对 agent 的元约束）
2. **本文（DEVELOPMENT.md）** — 协作与代码规范
3. 设计文档 `docs/superpowers/specs/2026-06-07-zotero-cli-design.md` — 架构与功能规范
4. 上游库默认行为（pyzotero / webdav4 / Typer 等）

**冲突处理原则**：发现本文与设计文档冲突时，先在 PR 描述里指出，由 reviewer 决定改设计还是改本文。**不要静默选一边实施**。

**语言**：本文与设计文档统一中文。代码、commit message、PR 描述用英文（便于工具处理与跨平台搜索）。

---

## §2. 项目脉络速览

zotero-cli 是单用户、agent-first 的 Zotero 命令行工具，覆盖三大场景：

- **C/D**：文献管理 + PDF 上传（默认 Zotero File Storage，配 `[<profile>.webdav]` 时切换为自实现 WebDAV 协议）
- **A/B/E**：检索、引用导出、笔记管理
- **RSS**：直接读 `zotero.sqlite` 只读模式，列订阅 + 查条目

**入口顺序**（agent 接到任务先按这顺序读）：

1. 本文 → 了解协作约定
2. 设计文档 §1–§5 → 项目目标、技术栈、目录结构、配置
3. 设计文档对应你任务的章节（如做 WebDAV → §10；做 RSS → §11）
4. 设计文档 §13 → 阶段实施顺序，确认你的任务在哪个阶段、依赖什么

**当前阶段定位**：项目尚无源码，处于设计文档已定稿、即将进入阶段 1 的状态。

---

## §3. 工程基线

### §3.1 工具链

| 项 | 选型 | 备注 |
|---|---|---|
| Python | 3.11+ | 用 `tomllib` 读 TOML、`Literal` 类型 |
| 包管理 | uv 0.4+ | `uv sync` / `uv add` / `uv run`，**禁止用 pip 直接装** |
| Lint + Format | ruff | 见下方配置 |
| 类型检查 | mypy strict | 全项目开启，不分阶段放宽 |
| 测试 | pytest + pytest-mock + respx | 详见 §6 |
| 提交前自检 | 本地手跑（无 CI 的兜底）| 见 §6.6（命令清单）+ §7.4（合并前流程） |

### §3.2 ruff 约定

写进 `pyproject.toml` 的 `[tool.ruff]`：

- `target-version = "py311"`
- `line-length = 100`
- 启用规则集：`E`、`F`、`W`、`I`（imports）、`UP`（pyupgrade）、`B`（bugbear）、`SIM`（simplify）、`RUF`
- `[tool.ruff.lint.isort]` 用三段式：标准库 / 第三方 / 项目内（`known-first-party = ["zotero_cli"]`）
- format 用 ruff-format（替代 black）

### §3.3 mypy strict 模式

写进 `pyproject.toml` 的 `[tool.mypy]`：

- `strict = true`（一次性开齐）
- `python_version = "3.11"`
- 第三方库无 stubs 时单独在 `[[tool.mypy.overrides]]` 写 `ignore_missing_imports = true`，**禁止全局放宽**
- 不允许 `Any` 隐式回退，必须显式标注 `Any` 才能用

### §3.4 依赖管理纪律

- 主依赖只有设计 §3.1 列出的那几项（typer / pyzotero / webdav4 / pydantic-settings / tomli-w）。**新增依赖必须先在 PR 描述里给理由**，包括为什么不能用现有依赖或 stdlib 实现，reviewer 同意后再加
- 测试相关依赖进 `[project.optional-dependencies] dev`；WebDAV 协议级集成测试相关进 `webdav-test`（见设计 §3.1 / §12.0 fallback 路径 3）
- **禁止隐式升级**：不在主分支主动改主依赖版本下限。要升级先单独开 PR，说明升级理由
- **禁止用 pip / poetry / pipenv**：项目统一 uv，混用会让 lockfile 漂移

---

## §4. 代码规范

### §4.1 命名

| 对象 | 风格 | 示例 |
|---|---|---|
| 模块文件 | 小写下划线 | `attachment_service.py` |
| 函数 / 变量 | snake_case | `select_backend`、`storage_path` |
| 类 | PascalCase | `AttachmentService`、`ProfileConfig` |
| 常量 | UPPER_SNAKE | `DEFAULT_TIMEOUT_SECONDS`、`MAX_PARALLEL_UPLOADS` |
| 私有 | 单下划线前缀 | `_select_backend`、`_to_start_bound` |
| 类型别名 | PascalCase | `UploadResult`、`DateRange` |

模块名与设计 §4 目录树一一对应，不自创。

### §4.2 类型标注

- 所有公开函数（不以 `_` 开头）必须有完整签名：参数 + 返回值
- `dict` 返回值用 `TypedDict` 或 pydantic 模型，**禁止裸 `dict[str, Any]` 作为对外返回**
- 字符串枚举用 `Literal["zfs", "webdav"]`（见设计 §10.0），不要用裸 `str`
- 私有辅助函数可以省签名，但不允许"半标注"（部分参数有、部分没有）

**Adapter boundary 例外（dict alias）**：当 adapter 透传外部库的动态 schema 数据（pyzotero item dicts、TOML 文档、原始 zotero.sqlite row 等），允许用**显式命名的 TypeAlias** 替代裸 `dict[str, Any]`，让 reviewer 一眼看出"这是边界透传，不是被忽略的 typing"。命名约定：

| 来源 | TypeAlias 名（在对应 adapter 模块顶部定义） |
|---|---|
| pyzotero 返回的 item / collection / response | `PyzoteroResponse: TypeAlias = dict[str, Any]` |
| pyzotero `item_template(...)` 模板 | `PyzoteroTemplate: TypeAlias = dict[str, Any]` |
| `tomllib.loads(...)` 解析结果 | `RawTomlDocument: TypeAlias = dict[str, Any]` |
| `sqlite3.Row` 转 dict（少量临时使用） | 改用 `Mapping[str, Any]` 或显式 TypedDict |

services 层在拿到 adapter 返回的 alias 后，**必须**装到 `models/results.py` 的 TypedDict 里再向上层传递——alias 只允许出现在 adapter 公开 API 与 service 内部第一个变量之间。


### §4.3 错误处理

错误流向严格三层：

```
adapters → 捕获外部库异常 → 翻译成 models/errors.py 中的 CLI 错误类
services → 不二次包装 adapter 错误，直接传播
commands → 最外层捕获 → 渲染 envelope + 设置退出码
```

具体规则：

- **禁止** `raise Exception(...)` / `raise RuntimeError(...)`，所有抛出走 `models/errors.py` 定义的错误类
- adapter 层的异常翻译参照设计 §10.0.2.6（pyzotero）和 §10.0.4（WebDAV）的映射表
- service 层不写 try/except 转码，让 adapter 层抛出的 CLI 错误直接透传
- command 层只在最外层包一次 try/except，渲染输出后调 `sys.exit(<code>)`

### §4.4 注释

**默认不写**。只在以下情况写一行：

- 行为非显然且代码无法自描述（如"为什么这里要 sleep 5s"）
- 协议字节级要求（如 prop XML 的属性顺序，参见设计 §10.1）
- 引用设计文档章节（如 `# 见设计 §10.5 场景 B`）

**禁止**：

- docstring 复述函数名（"`def get_user(): """获取用户"""`"）
- 注释里写"已修复 bug XXX"、"@author"、修改时间
- 注释掉的死代码（直接删，git 有历史）
- TODO 不带 issue/PR 链接（无追踪的 TODO 等于不存在）

### §4.5 文件 / 函数大小

软约束（提醒，不硬卡）：

- 模块超过 300 行 → 先想能不能拆成两个语义清晰的子模块
- 单方法超过 50 行 → 拆出辅助函数
- service 单方法同时调 ≥3 个 adapter 方法且做格式化 → 切分成"调 adapter"和"组装结果"两步

如果当前任务必须超出上限，在 PR 描述说明理由。

---

## §5. 分层纪律

设计 §4 的目录结构是**强约束**，违反 = PR 直接打回。

### §5.1 调用方向

```
commands/  →  services/  →  adapters/  →  外部世界（pyzotero、webdav4、sqlite3）
   ↓            ↓             ↓
   ↓          models/  ←  utils/
   ↓            ↑
   └────────────┘  （commands 也可 import models / utils）
```

**箭头方向不可逆**：

- `services/` 不允许 `import` `commands/`
- `adapters/` 不允许 `import` `services/` 或 `commands/`
- `models/` 不允许 import 任何项目其他模块
- `utils/` 允许 import `models/`（数据依赖，无行为耦合）；不允许 import services / adapters / commands

> **utils → models 例外说明**：`utils/output.py` 渲染 envelope，必须知道 `Envelope` shape；`utils/audit_log.py` 接受错误码常量。但 utils 仍**不**允许 import services / adapters / commands（避免反向耦合）。所有 utils/ 的"行为"必须可由调用方注入或可纯函数化（`render` 返回字符串、`write_entry` 接收 path 参数）。

### §5.2 各层职责

| 层 | 允许做 | 禁止做 |
|---|---|---|
| `commands/` | 参数声明（Typer）、调用 service、格式化输出（调 `utils/output.py`）、`sys.exit` + 写 stdout/stderr、共享命令层基础设施（如 `commands/_runner.py`） | 业务逻辑、直接调 pyzotero / webdav4 / sqlite3 |
| `services/` | 协调多个 adapter、组合数据、应用业务规则（如失败回滚策略） | 直接打 HTTP / SQL、写文件 I/O、import Typer/Rich |
| `adapters/` | 唯一允许 import `pyzotero` / `webdav4` / `sqlite3` 的层；翻译异常；本地配置文件读写（`config_store.py`）；只读 SQLite | 业务规则判断、跨 adapter 协调 |
| `models/` | 定义 pydantic / TypedDict / dataclass、纯校验逻辑 | 任何 I/O、import 项目其他模块 |
| `utils/` | 日期解析、输出格式化（`render` 返回字符串）、退出码常量、字段过滤、JSONL 审计日志；可 import `models/` 用于类型；受限 I/O：`audit_log.py` 可写日志文件、`process_check.py` 可读 `/proc` 等本地状态 | `sys.exit`、直接写 stdout/stderr、import services / adapters / commands |

> **`sys.exit` / stdout / stderr 在哪里写？** 只在 `commands/` 层。`utils/output.py` **返回字符串**（让 caller 决定写到哪、是否 exit）。`commands/_runner.py` 是命令层共享的 runner，它做 timing、catch CLIError、调 `render(...)` 拿字符串、写 stream、`sys.exit`。**runner 不在 utils/**——它有副作用（exit、write streams）且严格服务于 CLI 命令路径，归 commands。

### §5.3 共享代码归属

新写一段代码不知道放哪？按这个顺序问自己：

1. 它有没有 I/O / 调外部库？→ 有 = `adapters/`
2. 它会调 `sys.exit` 或写 stdout/stderr？→ 是 = `commands/`（典型：`commands/_runner.py`）
3. 它是数据结构定义吗？→ 是 = `models/`
4. 它是纯函数（无副作用）吗？→ 是 = `utils/`（可 import `models/` 取类型）
5. 它协调多个 adapter？→ 是 = `services/`
6. 都不是？→ 重新审视，多半是设计有歧义，找 reviewer

---

## §6. 测试纪律

### §6.1 严格 TDD 模块清单

下列模块**必须先写失败测试再写实现**，commit 粒度 = 一个失败测试到通过：

- `utils/date_parser.py`（设计 §11.4 / §12.4 要求 100% 覆盖）
- `adapters/webdav_client.py`（协议字节级一致性，设计 §12.4 要求 95%+）
- `adapters/sqlite_reader.py`（LEFT JOIN 正确性、`include_undated` 参数化，设计 §12.4 要求 90%+）
- `utils/output.py`（多格式渲染、字段过滤）
- `models/envelope.py`（JSON envelope 结构契约）

**TDD 节奏**：

```
1. 写一个失败测试（明确表达"应该做什么"）→ commit "test: <case>"
2. 写最少代码让它通过 → commit "feat: <impl>"
3. 重构（如有）→ commit "refactor: <reason>"
```

### §6.2 可先写后测的模块

CLI 路由层（`commands/*.py`）和 Rich 渲染细节可以先写实现，但**合并前**必须达到设计 §12.4 的覆盖率目标：

- `commands/*` ≥ 70%
- `services/*` ≥ 85%
- 总体 ≥ 85%

### §6.3 Mock 策略

按设计 §12.0 三级 fallback：

1. **优先 respx**：拦截 httpx 层
2. **Adapter mock**：respx 覆盖不到时，用 `pytest-mock` 在 `adapters/` 边界 patch
3. **本地测试 server**：协议级验证用 `pytest-httpserver` / `wsgidav`（仅当装了 `webdav-test` extra）

**新模块第一个测试要先验 respx 是否覆盖**——结果决定后续测试栈走向。验证方式：跑测试 + 抓 `respx` mock 是否命中，命中则继续用 respx，否则切换到 adapter mock。

### §6.4 Fixture 约定

- `tests/fixtures/` 下提交真实 SQLite + sample data（设计 §12.3）
- `build_sqlite.py` 是构造脚本，与 `zotero_test.sqlite` 同时入库
- **禁止**在测试里硬编码 SQL 查询结果模拟数据库——SQLite 用 fixture，不 mock cursor
- sample PDF 用 `tests/fixtures/sample_pdf.pdf`（小文件，几 KB 即可），不下载真实论文
- prop XML sample 进 `tests/fixtures/sample_prop.xml`，与协议实测结果对照

### §6.5 测试命名

```
test_<被测函数>_<场景>_<期望>
```

示例：

- `test_date_range_to_sql_bounds_year_only_returns_full_year`
- `test_select_backend_no_webdav_section_returns_zfs`
- `test_attachment_service_zfs_force_flag_raises_mutually_exclusive`
- `test_webdav_client_storage_path_trailing_slash_normalized`

不允许 `test_1`、`test_basic`、`test_works` 这类无信息名。

### §6.6 自检命令清单

提交前本地依次跑（**四项全过才算自检通过**）：

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --cov=src --cov-report=term-missing
```

把每项的输出（pass/fail + 关键数字）写进 PR 描述（见 §8）。

---

## §7. Git 与协作流程

### §7.1 默认走主干

下列阶段在 `main` 分支线性推进（不开 feature 分支）：

- **阶段 1**：基础设施（models/errors、models/envelope、utils/exit_codes、utils/output、utils/audit_log、utils/date_parser）
- **阶段 2**：配置层（models/config、commands/config）
- **阶段 6**：收尾（commands/schema、README）

理由：这些任务彼此依赖紧、且会改公共骨架，分支并行只会制造合并冲突。

**主干 commit 要求**：

- 每个 commit 必须独立通过 ruff + mypy + 当前已写的 pytest（不能"先 push 一半"）
- commit 粒度小：一个测试到一个 feature，不要把多次重构压成大 commit
- 写 commit 之前先 `git status` 确认没误把生成文件、临时文件入库

### §7.2 Conventional Commits

格式：

```
<type>(<scope>): <subject>

<body, optional>
```

`type`：

| type | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | bug 修复 |
| `refactor` | 不改外部行为的内部重构 |
| `test` | 仅加/改测试 |
| `docs` | 仅改文档（含 DEVELOPMENT.md / README） |
| `chore` | 工具配置、依赖升级、目录调整 |
| `spike` | spike 分支上的探索性 commit；spike 结论文档进主干时改用 `docs(spike): ...` |

`scope`：取设计 §4 目录最后一级（`date_parser` / `webdav_client` / `attachment_service` / `config` / 等），跨多模块时用 `core`。

示例：

- `feat(date_parser): support open-ended ranges (X.. and ..Y)`
- `fix(webdav_client): strip trailing slash from storage_path`
- `test(envelope): add affected_keys edge cases`
- `refactor(attachment_service): extract _select_backend helper`

subject 控制在 72 字符以内，不带句号。

### §7.3 独立模块走 feature branch / worktree

适用范围（满足下列**全部**条件才能开分支）：

1. 该模块是设计 §13 的"独立可孤立开发"模块（典型：`webdav_client`、`sqlite_reader`、`date_parser`、`output`、`envelope`、`audit_log`）
2. 该模块依赖的 adapters / models / utils 在 `main` 上**已经就位**
3. 该任务**只改自己模块的文件**（不改其他模块、不改 pyproject.toml、不改公共类型定义）

任意一条不满足 → 留在 `main` 推进。

**分支命名**：

```
feat/<模块>      ← 新功能：feat/webdav-client
fix/<模块>-<简述> ← bug 修：fix/date-parser-leap-year
spike/<主题>      ← spike：spike/pyzotero-attachment-api
```

**worktree 用法**（推荐，与 `main` 工作目录隔离）：

```bash
# 创建（在主仓目录执行）
git worktree add ../zotero-cli-webdav feat/webdav-client

# 在 worktree 里干活
cd ../zotero-cli-webdav
# ... 写代码、跑测试、commit ...

# 合并回 main（rebase 流程见 §7.5）
cd /path/to/main
git merge --ff-only feat/webdav-client

# 删除 worktree
git worktree remove ../zotero-cli-webdav
```

### §7.4 合并前自检

合并 feature 分支到 `main` 之前，**在 feature 分支上**：

1. rebase 到最新主干：
   - 有 remote：`git fetch origin && git rebase origin/main`
   - 仅本地仓：`git rebase main`
2. 跑完整 §6.6 自检命令清单
3. 跑过的指标写进 PR 描述（§8 模板）
4. 用 `--ff-only` 合并（避免无意义的 merge commit）

**不允许**：

- 用 `git merge` 把 main 拉进 feature（让历史变线状是 reviewer 友好的）
- 用 `--no-verify` 绕过 hook（项目目前没装 pre-commit hook，将来加了也不许绕）
- 用 `git push --force` 到 `main`（永远）

### §7.5 何时该开分支：决策流程

```
任务到手
  │
  ├─ 是设计 §13 的"独立模块"任务吗？
  │    │
  │    ├─ 否 → 留主干（§7.1）
  │    └─ 是 → 继续
  │
  ├─ 它依赖的 adapters/models/utils 在 main 上都就位了吗？
  │    │
  │    ├─ 否 → 留主干，先把依赖补上
  │    └─ 是 → 继续
  │
  ├─ 该任务只改自己模块的文件吗？
  │    │
  │    ├─ 否 → 留主干（避免分支间冲突）
  │    └─ 是 → 开 feature 分支 / worktree
```

### §7.6 设计偏离处理

实施过程中发现设计文档有歧义、矛盾、不可实现的地方：

1. **不要静默改设计**也**不要硬着头皮按错的实施**
2. 在 PR 描述里专门开一段 "设计偏离 / 设计提议"，写：
   - 引用的设计章节（如 §10.5 场景 B）
   - 发现的问题（具体到字段、行为）
   - 你的建议（改设计 / 改实现 / 加 spike 验证）
3. 等 reviewer 决定方向，再继续

---

## §8. PR / 合并描述模板

写给同行 agent 读。目的：**让 reviewer 不必跑测试就能判断能不能合**。

```markdown
## 改动概览

<一句话讲清楚做了什么。引用设计章节，如"实现 §10.2 WebDAV 完整上传流程的 Step 4"。>

### 涉及文件

- `src/zotero_cli/adapters/webdav_client.py` — 新增 PROPFIND/MKCOL/PUT/DELETE 包装
- `tests/unit/test_webdav_client.py` — 27 个新增 case，覆盖 storage_path normalize / zip 构造 / prop XML

## 自检结果

- [x] `ruff check`：0 errors
- [x] `ruff format --check`：clean
- [x] `mypy src`：0 errors（strict 模式）
- [x] `pytest --cov=src`：143 passed, 0 failed
- [x] 覆盖率：本次新增模块 96%（目标 95%）；总体 87%（目标 85%）

## 关联设计章节

- 主要：§10.1 协议布局、§10.2 上传流程、§10.5 场景 B md5 检测
- 边角：§10.6 风险点 1（base64）、风险点 4（storage_path 默认值）

## 阶段验收 checklist 进度

参照 §9 阶段 4 checklist：

- [x] WebDAV 客户端核心方法（PROPFIND/MKCOL/PUT/DELETE/GET）
- [x] storage_path normalize 逻辑 + 校验失败抛 CONFIG_INVALID
- [x] zip 构造（base64 文件名 + ZIP_STORED）
- [x] prop XML 生成与解析（字节级一致）
- [ ] 协议 spike 实测（待阶段 4 单独 PR）

## 设计偏离 / 提议

<如有>。无则写"无"。

## 已知遗留 / 后续 TODO

- attachment_service 还没接进来（独立任务，见 issue/PR #X）
- WebDAV 并发上传（设计 §10.4）未实现，等单文件路径稳定再加
```

**不要**写：

- "Refactored some code" 这种无信息描述
- 复制粘贴 git diff 当描述
- "All tests pass" 不报数字
- 把 TODO 藏在代码注释里不写进 PR 描述

---

## §9. 阶段验收 checklist

按设计 §13 拆解。每个阶段是一个独立的"完成定义"。**人在阶段门按这个清单 review**，agent 提交时按这个清单自检。

### §9.1 阶段 1：基础设施

- [ ] `pyproject.toml` 写好依赖 + ruff + mypy 配置（§3.2 / §3.3）
- [ ] `uv sync` 成功，`uv run python -c "import zotero_cli"` 不报错
- [ ] `models/errors.py` 定义所有 §9.2 错误码对应的异常类，每类有 `code`、`category`、`exit_code` 属性
- [ ] `models/envelope.py` 定义 `Envelope`、`ErrorObject`、`MetaObject` 的 pydantic 模型，与设计 §8 字段一一对应
- [ ] `utils/exit_codes.py` 定义所有退出码常量
- [ ] `utils/output.py` 框架：能根据 `(data, command_name, json_mode, all_fields, quiet)` 路由到 5 种格式（kv / kv-list / tree / yaml / summary / json）；`--quiet` 与 `--json` 互斥校验
- [ ] `utils/audit_log.py`：JSONL 写入、单文件 10MB 自动压缩归档（设计 §9.4）
- [ ] `utils/date_parser.py`：完整实现设计 §11.4，覆盖率 100%
- [ ] 所有上述模块的单元测试齐全
- [ ] 自检四项全过

### §9.2 阶段 2：配置层

- [x] `models/config.py`：~~pydantic-settings~~ Config 主模型（BaseModel + 手写 ENV 覆盖）+ `ProfileConfig` / `WebDAVConfig` / `SQLiteConfig` / `ItemFieldsConfig` / `FeedItemFieldsConfig` 子模型
  - **设计偏离**：未使用 pydantic-settings BaseSettings。原因：`ZOTERO_CLI_<PROFILE>_<KEY>` 命名约定需要 profile 名动态注入，`BaseSettings` 的 `env_nested_delimiter` 不直接支持。ENV 覆盖逻辑在 `config_service.py` `_apply_env_overrides()` 实现。
- [ ] `WebDAVConfig.storage_path` 的 normalize validator（设计 §10.1）：空字符串 ✓、`/` 开头无尾随 ✓、拒绝单 `/` / `..` / `//`
- [ ] `Config.model_validator` 校验 WebDAV + library_type 兼容性矩阵（设计 §10.0.1）
- [ ] 环境变量覆盖：`ZOTERO_CLI_<PROFILE>_<KEY>` 嵌套覆盖（设计 §5.3）
- [ ] SQLite 路径自动检测（设计 §5.4）：config 显式 → `ZOTERO_DATA_DIR` → 平台默认（含 Snap/Flatpak）
- [ ] `commands/config.py`：`init`、`show`、`set`、`get`、`validate`、`profiles` 六个子命令
- [ ] `config validate` 实现兼容性矩阵校验，`library_type=group + [webdav]` 报 `UNSUPPORTED_LIBRARY_TYPE`
- [ ] 配置文件权限 0600（创建时设置）
- [ ] 单元 + 集成测试齐全
- [ ] 自检四项全过

### §9.3 阶段 3：Zotero API 适配（pyzotero）

**前置 spike（必做）**：

- [ ] `docs/superpowers/specs/spikes/pyzotero-attachment-api.md` 完成
- [ ] spike 验证：§10.0.2.1 表格四个 API 的实际行为是否与文档一致
- [ ] spike 验证：`upload_attachments(parentid=None, template['key']=existing_key)` 真能"重传到已有 attachment"
- [ ] spike 验证：`unchanged` 返回时确实没有发生网络上传（respx 抓包）
- [ ] spike 验证：respx 是否能拦截 pyzotero 的 httpx 请求（决定 §6.3 mock 策略）
- [ ] **spike 与设计冲突时回头修订设计 §10.0.2 再继续**

**实施**：

- [ ] `adapters/zotero_api.py`：pyzotero 包装 + `_select_backend(profile)` 派发 + 异常映射（§10.0.2.6）
- [ ] `services/item_service.py` + `commands/items.py`（不含 attach；create/update/delete 接审计日志）
- [ ] `services/collection_service.py` + `commands/collections.py`（写操作接审计日志）
- [ ] `services/tag_service.py` + `commands/tags.py`（写操作接审计日志）
- [ ] `services/export_service.py` + `items export`
- [ ] `meta.affected_keys` 计算规则正确（设计 §7.2.1）：unchanged / failed 不进
- [ ] `--quiet` 模式下 affected_keys 为空时 stdout 完全空（0 字节）
- [ ] `--quiet` 与 `--json` 互斥校验
- [ ] 单元 + 集成测试齐全
- [ ] 自检四项全过

### §9.4 阶段 4：附件上传（ZFS + WebDAV）

**前置 spike（已通过对齐 zotero-mcp 参考实现完成）**：

- [x] `docs/superpowers/specs/spikes/phase4-open-issues.md` 完成 — 调研报告含 7 项协议对比
- [x] spike 验证：ZIP 文件名格式 — 与 zotero-mcp 一致（原始文件名，非 base64）
- [x] spike 验证：ZIP 压缩方式 — 与 zotero-mcp 一致（ZIP_DEFLATED）
- [x] spike 验证：mtime 一致性 — 与 zotero-mcp 完全一致（`int(st_mtime * 1000)`）
- [x] spike 验证：prop XML 字节级格式 — 与 zotero-mcp 字节级一致
- [x] spike 验证：respx 可拦截 webdav4 — 已验证可用
- [x] spike 验证：storage_path 默认值与变体（`""`、`/zotero`）— 实现合理

**实施**：

- [x] `adapters/zotero_api.py` 扩展：attachment_simple/both/upload_attachments/item_template 包装
- [x] `adapters/webdav_client.py`：webdav4 包装 + zip 构造（原始文件名、`ZIP_DEFLATED`）+ prop XML 生成解析 + storage_path normalize + 路径遍历防护（Zotero key regex）+ defusedxml XXE 防护
- [x] `services/attachment_service.py`：`_select_backend()` 派发 + §10.0.1 前置校验 + ZFS/WebDAV 双路径 + 回滚 + ThreadPoolExecutor 并发
- [x] `items create --attach` / `items update --attach`（场景 A，两后端都支持）
- [x] `items attach`（含 `--reuse-key` 场景 B 重传 + `--force` 仅 WebDAV 有效；ZFS 后端 `--force` 报 `MUTUALLY_EXCLUSIVE_ARGS`）
- [x] envelope `data.uploaded[]` / `unchanged[]` / `failed[]` schema (`models/attachment.py`)
- [x] `failed[]` 用独立 schema（`AttachmentFailedItem` TypedDict）
- [x] `meta.affected_keys` 按 §8.3.1 规则计算
- [x] WebDAV 多文件并发（设计 §10.4）：`ThreadPoolExecutor(max_workers=4)`
- [ ] 设计 §12.5 手动测试清单中的附件相关项全部通过（需真实账号，不阻塞验收）
- [x] 单元 + 集成测试齐全（359 tests）
- [x] 自检四项全过（ruff clean, mypy strict 0 errors, 359 passed）

### §9.5 阶段 5：RSS（SQLite）

- [x] `adapters/sqlite_reader.py`：`mode=ro&nolock=1` 连接 + schema 兼容性检测（设计 §11.6）+ 启动时缓存 fieldID
- [x] `services/feed_service.py`：list + items + date 过滤（SQL 端完成）+ `include_undated` 参数化（设计 §11.3.2）
- [x] `commands/feeds.py`：`list` / `show` / `items`，`feed-id` 整数参数（= `feeds.libraryID`）
- [x] `FeedItem` 模型含 `feed_id` 字段（设计 §11.2）
- [x] 集成测试用 `tests/fixtures/zotero_test.sqlite`（设计 §12.3 五条覆盖各种 date 格式）
- [x] 性能测试：1000 条 feed items + date 过滤 < 300ms（设计 §11.7）
- [x] 单元 + 集成测试齐全（525 tests）
- [x] 自检四项全过（ruff clean, ruff format clean, mypy strict 0 errors, 525 passed）

### §9.6 阶段 6：Agent 自省 + 收尾

- [x] `commands/schema.py`：命令树 JSON Schema 自省，`--command <name>` 输出指定子命令 schema（含参数提取、dot-notation、强制 JSON envelope）
- [x] `README.md`：安装、快速开始、典型 agent 调用例子
- [x] 设计 §12.5 手动测试清单：15/17 已执行，14 PASS、1 PASS（ZFS --reuse-key，pyzotero 1.13.1 修复后已解除 guard）、2 SKIP（需 Zotero 桌面客户端）
- [x] 全模块覆盖率达到设计 §12.4 目标（当前 94%，webdav_client 97%、zotero_api 96%、attachment_service 95%）
- [x] 审计日志格式与设计 §9.4 一致，10MB 轮转生效
- [x] mypy strict 全项目无 error
- [x] ruff 全项目 clean（ruff check + ruff format --check 均通过）
- [ ] DEVELOPMENT.md 与设计文档已根据实施过程发现的偏离同步更新（见 §12 修订记录）

---

## §10. 安全与敏感信息

### §10.1 配置文件

- `~/.config/zotero-cli/config.toml` 创建时即设 `0600`（设计 §5.1）
- 任何写配置的命令（`config init` / `config set`）必须在写入后再次 `chmod 0600` 兜底

### §10.2 审计日志

按设计 §9.4：

- 只记录写操作（create/update/delete/attach）
- API key 记录前 4 位 + 掩码：`abc1****`
- WebDAV 密码、PDF 文件内容**永不记录**
- 失败也要记录（含错误码、错误消息）

### §10.3 测试 fixture

- **禁止**在 fixture 里塞真实 API key、真实 WebDAV 凭证
- 用占位符：`api_key = "test_api_key_placeholder"`、`password = "test_password"`
- 真实账号测试只能在 E2E 阶段，靠环境变量注入（不入库）
- `tests/fixtures/zotero_test.sqlite` 用 `build_sqlite.py` 构造的虚构数据，**不导出真实 Zotero 数据库**

### §10.4 提交前自检

每次 `git commit` 前手动执行：

```bash
# 检查暂存区是否意外含敏感信息
git diff --cached | grep -iE "api[_-]?key|password|secret|token" \
  | grep -v "test_\|placeholder\|example\|<" \
  || echo "OK"
```

任何匹配（除测试占位符）都要在提交前清理。

### §10.5 临时文件

- 测试中产生的临时文件用 `tmp_path` fixture，pytest 自动清理
- 调试用的实际 PDF / SQLite 数据库**不入库**，加进 `.gitignore`：
  ```
  *.pdf
  *.sqlite
  *.sqlite-journal
  audit.log*
  ```
  例外：`tests/fixtures/sample_pdf.pdf`、`tests/fixtures/zotero_test.sqlite` 显式 `git add -f`

---

## §11. 术语速查

| 术语 | 含义 |
|---|---|
| ZFS | Zotero File Storage，Zotero 官方文件存储，由 pyzotero 内建实现 |
| WebDAV 后端 | 用户配 `[<profile>.webdav]` 时启用的自实现 WebDAV 协议路径 |
| profile | 一组配置（API key、library、WebDAV 等），可有多个，默认 `default` |
| `affected_keys` | envelope `meta` 字段，列**实际改变服务端状态**的资源 key（设计 §7.2.1 / §8.3.1） |
| 场景 A | "新建 attachment"（`items create --attach` / `items update --attach` / `items attach`，无 `--reuse-key`） |
| 场景 B | "重传已有 attachment"（仅 `items attach --reuse-key <key>`） |
| spike | 对未确定假设的小型实测验证，结果记录在 `docs/superpowers/specs/spikes/` |

---

## §11.5 已知限制

### ZFS 后端 `--reuse-key`（已由 pyzotero 1.13.1 修复）

**背景**：使用 ZFS 后端执行 `items attach <parent> <file> --reuse-key <key>` 曾因 pyzotero 上游 bug（`Zupload._register_upload` 硬编码 `If-None-Match: *` 导致 HTTP 412）而不可用。上游 issue #322 已在 pyzotero 1.13.1 中修复——`_register_upload` 现在接收 `md5` 参数，有 md5 时发送 `If-Match`，否则发送 `If-None-Match: *`。

**当前状态**：项目已移除临时 guard（原 `attachment_service.py:59-67` 的 `TODO` 块）。ZFS `--reuse-key` 路径现已生效：读取已有 attachment 的 md5，填入 `item_template`，调用 `upload_attachments([tpl], parentid=None)`，匹配 pyzotero 1.13.1 的 `If-Match` 流程。

**WebDAV 后端不受影响**：WebDAV `--reuse-key` 完全由本项目自行实现 upload 协议，不经过 pyzotero 的三步上传流程。

---

## §12. 修订记录

| 日期 | 改动 | 触发原因 |
|---|---|---|
| 2026-06-07 | 初稿 | 设计文档定稿、进入实施前确立协作规范 |
| 2026-06-09 | WebDAV ZIP：设计 §10.1 写 base64 编码内部文件名 + `ZIP_STORED`，实际实现使用原始文件名 + `ZIP_DEFLATED` | Phase 4 spike 验证：参考实现 (zotero-mcp) 使用原始文件名 + DEFLATED，且桌面端能正常打开；base64 假设未经实测，跟从已验证方案 |
| 2026-06-09 | `items create/update --attach` 响应使用附件契约 (`data.uploaded[]`) 而非 CRUD 契约 (`data.successful[]`)，`meta.affected_keys` 合并父 item 和 attachment key | 代码评审 R2：对齐设计 §8.3 / §8.3.1 附件响应契约 |
| 2026-06-09 | ZFS `--reuse-key` 增加临时 guard 阻断并提示用户配置 WebDAV；`_attach_zfs` template 补充 `md5` 字段 | §12.5 手动测试发现 pyzotero `_register_upload` 硬编码 `If-None-Match: *`（上游 issue #322） |
| 2026-06-09 | 移除 ZFS `--reuse-key` 临时 guard；更新 §11.5 已知限制状态为"已修复" | pyzotero 1.13.1 修复上游 issue #322，`_register_upload` 接收 `md5` 参数 |



