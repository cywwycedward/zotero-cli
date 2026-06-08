# zotero-cli 设计文档

**创建日期**：2026-06-07
**状态**：待实施

## 1. 项目目标与定位

### 1.1 一句话定位
单用户、agent-first 的 Zotero 命令行工具，核心覆盖文献管理、PDF 上传（默认走 Zotero File Storage，配了 WebDAV 则走自实现的 WebDAV 协议）和 RSS 订阅查询三大场景。

### 1.2 目标用户
- 主要使用者：CLI 默认输出格式给 **agent** 调用（简洁、易解析）
- 次要使用者：`--json` 模式给**人类写脚本**用（完整、可 jq 处理）

### 1.3 不做的事
- 不实现 Streaming API（WebSocket 实时推送）
- 不实现 OAuth 流程（用户手动配置 API key 即可）
- 不做 mark-read（RSS 已读标记）
- 不做 feed → library 转存
- **不在同一 profile 内提供 ZFS / WebDAV 切换开关**：上传后端由 `[<profile>.webdav]` 配置段是否存在自动决定（不存在 = 走 ZFS，由 pyzotero 内置实现；存在 = 走自实现 WebDAV 协议）。要在两者间切换就改 config 或换 profile。

---

## 2. 功能范围

| 模块 | 优先级 | 实现方式 |
|---|---|---|
| **C - 文献管理整理** | 主要 | pyzotero 批量操作 |
| **D - PDF 上传** | 主要 | 默认 ZFS（pyzotero 内建）；profile 配 `[<profile>.webdav]` 时切换为自实现 WebDAV 协议 |
| **A - 检索浏览** | 基础 | pyzotero |
| **B - 导出引用** | 基础 | pyzotero（BibTeX/RIS/CSL JSON 等） |
| **E - 笔记管理** | 基础 | pyzotero |
| **RSS 只读查询** | 主要 | 直接读 zotero.sqlite（只读模式） |

RSS 子功能：
- 列出所有订阅源（`feeds list`）
- 查询订阅源条目，支持按 date 过滤（`feeds items <id> --date ...`）

---

## 3. 技术栈

| 层级 | 选型 | 版本 |
|---|---|---|
| Python | 3.11+ | stdlib `tomllib` 用于读取 |
| 包管理 | uv | 0.4+ |
| CLI 框架 | Typer | 0.12+ |
| 终端美化 | Rich | 13+ |
| HTTP 客户端 | httpx | 0.27+ |
| Zotero API | pyzotero | 1.5+ |
| WebDAV 客户端 | webdav4 | 0.10+ |
| 配置管理 | pydantic-settings | 2.2+ |
| TOML 写入 | tomli-w | 1.0+（`config init` / `config set` 使用，不保留注释、扁平/简单结构足够） |
| SQLite | stdlib `sqlite3` | - |
| 日期解析 | stdlib `re` + `datetime` + `calendar` | - （严格正则匹配，不引入外部库） |
| 测试 | pytest + pytest-mock + respx（默认 dev 组）；备选 pytest-httpserver / wsgidav（`webdav-test` 可选组，按 §12.0 fallback 路径 3 决定是否启用） | - |
| 代码质量 | ruff + mypy | - |

### 3.1 关键依赖清单（pyproject.toml）

```toml
[project]
dependencies = [
    "typer[all]>=0.12.0",
    "pyzotero>=1.5.0",
    "webdav4>=0.10.0",
    "pydantic-settings>=2.2.0",
    "tomli-w>=1.0.0",
    "pyyaml>=6.0",                         # config show 的 YAML 渲染（§7.3 yaml 格式）；选 pyyaml 而非自写：避免 corner case（多行字符串、特殊字符转义）拖累测试覆盖
]

[project.optional-dependencies]
# dev：日常开发与单元/集成测试（lint、type check、httpx mock、覆盖率）
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",                     # 自检命令 `uv run pytest --cov` 的依赖（DEVELOPMENT.md §6.6）
    "respx>=0.21",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-PyYAML>=6.0",                   # mypy strict 模式下 pyyaml 的 stubs；与 pyyaml 配套
]
# webdav-test：WebDAV 后端的协议级集成测试（仅在 §12.0 fallback 路径 3 启用时安装）
# 阶段 4 spike 先做 respx 覆盖性实测；如果发现 webdav4 请求拦截不到，再 `uv sync --extra webdav-test` 拉这两个库
webdav-test = [
    "pytest-httpserver>=1.0",
    "wsgidav>=4.3",
]
```

---

## 4. 目录结构与模块划分

```
zotero-cli/
├── pyproject.toml
├── README.md
├── docs/superpowers/specs/2026-06-07-zotero-cli-design.md
├── src/zotero_cli/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                        # Typer app 入口
│   ├── commands/                     # 命令层（薄）
│   │   ├── _runner.py                # 共享：GlobalOptions + run_command（timing + CLIError catch + stdout/stderr 分离 + sys.exit）；唯一允许 sys.exit / 写流的非命令文件
│   │   ├── items.py
│   │   ├── collections.py
│   │   ├── tags.py
│   │   ├── feeds.py
│   │   ├── config.py
│   │   └── schema.py
│   ├── services/                     # 业务逻辑层
│   │   ├── item_service.py
│   │   ├── collection_service.py
│   │   ├── tag_service.py
│   │   ├── attachment_service.py     # 协调 ZFS（pyzotero）/ WebDAV（自实现）两种后端
│   │   ├── feed_service.py           # RSS 查询
│   │   └── export_service.py
│   ├── adapters/                     # 外部系统封装
│   │   ├── zotero_api.py             # pyzotero 薄封装
│   │   ├── webdav_client.py          # webdav4 + Zotero 协议
│   │   ├── sqlite_reader.py          # zotero.sqlite 只读
│   │   └── config_store.py           # config.toml 读写 + permission 0600 + 环境变量覆盖；唯一允许在 services 之外读写本地配置文件的层
│   ├── models/                       # pydantic 模型
│   │   ├── config.py
│   │   ├── envelope.py
│   │   ├── item.py
│   │   ├── feed.py
│   │   └── errors.py
│   ├── utils/
│   │   ├── output.py                 # 格式化（kv/tree/yaml/summary/json）
│   │   ├── date_parser.py            # date 范围解析
│   │   ├── exit_codes.py
│   │   ├── audit_log.py
│   │   └── process_check.py
│   └── constants.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── zotero_test.sqlite
    │   ├── build_sqlite.py
    │   ├── sample_items.json
    │   ├── sample_pdf.pdf
    │   └── sample_prop.xml
    ├── unit/
    ├── integration/
    └── e2e/
```

**分层原则**：
- `commands/`：参数声明 + 调用 service，不写业务逻辑
- `services/`：协调多个 adapter 的业务逻辑
- `adapters/`：外部系统的薄封装，统一错误处理
- `models/`：所有 pydantic 模型
- `utils/`：纯函数工具

---

## 5. 配置管理

### 5.1 配置位置

`~/.config/zotero-cli/config.toml`（XDG 标准），文件权限 `0600`。

### 5.2 配置结构（含多 profile + 字段过滤）

```toml
[default]
api_key = "abc123def456xyz..."
library_id = "12345678"
library_type = "user"  # 或 "group"

# Item 列表输出时的字段过滤
[default.item_fields]
list = ["key", "title", "creators", "date", "itemType", "tags"]

# Feed Item 列表输出时的字段过滤
# 注：feed_id 在 RSS 模型里等于 feeds.libraryID（整数），用作命令参数传入
[default.feed_item_fields]
list = ["feed_id", "item_id", "title", "date", "url", "read_time"]

# WebDAV 配置（可选；不写则附件走 Zotero File Storage 默认通道）
# 写了之后：library_type 必须为 "user"，否则 config validate 报 UNSUPPORTED_LIBRARY_TYPE
# 详见 §10.0.1 兼容性矩阵
[default.webdav]
# url: WebDAV server 的 base URL（不包含 zotero 子路径）
# storage_path: Zotero storage 目录在 server 上的相对路径
#   - 必须以 / 开头（除非空字符串 ""，表示根目录）
#   - 末尾的 / 会被自动 strip（"/zotero/" → "/zotero"）
#   - 不允许仅 "/"、不允许 ".." 或 "//"
# 实际操作路径 = url + storage_path + "/<key>.{zip,prop}"
# 例：上传 ABC123.zip 到 https://dav.example.com/zotero/ABC123.zip
url = "https://dav.example.com"
storage_path = "/zotero"
username = "myuser"
password = "mypass"
timeout = 120
verify_ssl = true

[default.sqlite]
path = "/home/user/Zotero/zotero.sqlite"  # 不填则自动检测

[work]
api_key = "work_key_xyz..."
library_id = "87654321"
library_type = "group"
# ... 同上
```

### 5.3 环境变量覆盖

`ZOTERO_CLI_<PROFILE>_<KEY>` 格式覆盖任意配置项，例如：
- `ZOTERO_CLI_DEFAULT_API_KEY`
- `ZOTERO_CLI_WORK_WEBDAV_PASSWORD`

### 5.4 SQLite 路径自动检测优先级

1. config 显式 `[<profile>.sqlite] path`
2. 环境变量 `ZOTERO_DATA_DIR`
3. 平台默认路径（Linux/macOS `~/Zotero/zotero.sqlite`、Windows `%USERPROFILE%\Zotero\zotero.sqlite`、含 Snap/Flatpak 变体）

---

## 6. 命令树

全局 flag（位于子命令之前）：
- `--json`：切换为完整 JSON envelope 输出（脚本/jq 用）
- `--profile NAME`：切换 profile（默认 `default`）
- `--quiet` / `-q`：仅输出关键字段（如 itemKey 列表，每行一个），方便 `xargs` 管道；与 `--json` 互斥

```
zotero-cli [--json] [--profile NAME] [--quiet | -q] <command>

├── items
│   ├── list [--limit N] [--collection KEY] [--tag TAG] [--all-fields]
│   ├── search <query> [--limit N] [--all-fields]
│   ├── show <key> [--all-fields]
│   ├── create --type <itemType> --title <title>     # --title 是父 item 标题
│   │   [--creators <json>] [--date <date>] [--doi <doi>] [--url <url>]
│   │   [--tags <tag1,tag2>] [--collection KEY]
│   │   [--attach <file.pdf>]                        # 集成附件上传：每次都创建新 attachment
│   │   [--attach-title <attachment-title>]          # 附件 title（默认用文件名），与父 item 的 --title 解耦
│   │                                                # 后端由 config 决定（无 [webdav] = ZFS，有 = WebDAV，见 §10.0）
│   │   [--json-file <path>] [--dry-run]
│   ├── update <key>
│   │   [--title <title>] [--date <date>]
│   │   [--tags <tag1,tag2>] [--add-tags <tag1,tag2>]
│   │   [--json-patch <json>] [--attach <file.pdf>]   # --attach 同样总是新建 attachment
│   │   [--attach-title <attachment-title>]           # 同 create
│   │   [--dry-run]
│   ├── delete <key...> [--yes] [--dry-run]
│   ├── export --format <bibtex|ris|csljson|...>
│   │   [--collection KEY] [--tag TAG] [--output <file>]
│   └── attach <key> <file.pdf>
│       [--title <attachment-title>]        # 附件 title（默认用文件名）；本命令无父 item title 歧义
│       [--reuse-key <attachment-key>]     # 重用已有 attachment key（断点续传/重试上传中断）
│       [--force]                          # 仅 WebDAV 后端有效；ZFS 后端拒绝（MUTUALLY_EXCLUSIVE_ARGS，见 §10.0.2.3）
│       [--dry-run]
│
├── collections
│   ├── list
│   ├── show <key>
│   ├── create --name <name> [--parent KEY]
│   ├── update <key> --name <name>
│   ├── delete <key> [--yes]
│   ├── add-items <collection-key> <item-key...>
│   └── remove-items <collection-key> <item-key...>
│
├── tags
│   ├── list
│   ├── add <tag> <item-key...>
│   ├── remove <tag> <item-key...>
│   ├── rename <old-tag> <new-tag>
│   └── delete <tag> [--yes]
│
├── feeds
│   ├── list                                  # 输出含 feed_id 列（即 feeds.libraryID）
│   ├── show <feed-id>                        # feed-id = feeds.libraryID（整数）
│   └── items <feed-id>                       # feed-id = feeds.libraryID（整数）
│       [--date <date-filter>]                # 2024-06-15 / 2024-01..2024-12 / 2024 / ..2024-06
│       [--include-undated] [--limit N] [--all-fields]
│
├── config
│   ├── init [--profile NAME]
│   ├── show [--profile NAME]
│   ├── set <key> <value> [--profile NAME]
│   ├── get <key> [--profile NAME]
│   ├── validate [--profile NAME]
│   └── profiles
│
└── schema [--command <name>]
```

---

## 7. 输出系统

### 7.1 数据流

```
commands/  →  services/(纯数据)  →  utils/output.py(格式化)  →  Terminal
```

Service 层只返回 dict / list / pydantic 对象，不关心格式。`utils/output.py` 接收 `(data, command_name, json_mode, all_fields)` 决定格式。

### 7.2 格式映射表

| 命令模式 | 默认格式 | `--json` | `--quiet` |
|---|---|---|---|
| 列表类（items list/search、feeds items、tags list） | `kv-list` | `json` | 仅 key 列表（每行一个） |
| 单对象（items show、feeds show） | `kv` | `json` | 仅 key |
| 写操作（create/update/delete） | `summary` | `json` | 仅 `meta.affected_keys` 列表（每行一个，见 §7.2.1） |
| 附件上传（items create/update/attach with `--attach`）| `summary` | `json` | 仅 `meta.affected_keys` 列表（每行一个，见 §8.3.1） |
| 层级数据（collections list） | `tree` | `json` | 仅 collection key 列表 |
| 配置（config show） | `yaml` | `json` | 不支持（报 `MUTUALLY_EXCLUSIVE_ARGS`） |
| 导出（items export） | `raw`（原始 BibTeX/RIS/CSL JSON 字节，无 envelope） | `json`（envelope `data` 含 `format`+`content` 字符串） | 不支持（报 `MUTUALLY_EXCLUSIVE_ARGS`） |
| 自省（schema） | `json`（固定，**始终** envelope JSON，包括错误也走 stdout JSON） | `json` | 不支持（报 `MUTUALLY_EXCLUSIVE_ARGS`） |

**关于导出（export）行**：

- **默认格式 `raw`**：service 返回的字节直接写 stdout（或 `--output` 指定文件）。不加 envelope、不加换行包装、不做 base64。这是"最少惊喜"——agent 与人都期望 `zotero-cli items export --format bibtex > refs.bib` 直接拿到合法 `.bib` 文件
- **`--json`**：envelope `data` 形如 `{"format": "bibtex", "content": "<utf-8 字符串>", "byte_size": <int>}`；二进制格式（如未来加的 EndNote XML）用 `"content_b64": "<base64>"` 字段（互斥），文档自描述。
- **`--quiet` 不支持**：导出无 `key` 概念，也不属于"写操作"，硬 `MUTUALLY_EXCLUSIVE_ARGS`（退出码 64）。

**关于自省（schema）行**：

schema 命令的"`json` 固定"含义升级：**所有路径**——成功 / `--quiet` 拒绝 / `--command` 路径不存在——都输出 envelope JSON 到 stdout，stderr 永远为空。运行时强制 `json_mode=True`，与设计 §7.5 "json 模式 stdout 永远是合法 JSON envelope" 的承诺保持一致。

`--quiet` 与 `--json` 互斥：同时使用返回 `MUTUALLY_EXCLUSIVE_ARGS`（退出码 64）。

#### 7.2.1 `meta.affected_keys` 的统一定义

`affected_keys` 是 agent / 脚本管道的**核心契约**，所有写操作命令都遵循同一规则：

> `affected_keys` 列出本次调用**实际改变服务端状态**的所有资源 key（item / attachment / collection）。"未改变"的资源不进入。

| 操作结果分类 | 是否进 `affected_keys` |
|---|---|
| 新创建（`successful`/`uploaded`）| ✅ 进 |
| 已修改成功（`update`/`patch`）| ✅ 进 |
| 已删除成功（`delete`）| ✅ 进（即便服务端资源已不存在）|
| `unchanged`（远端 md5 一致、字段值未变化等无操作情况） | ❌ 不进 |
| `failed`（任何形式的失败） | ❌ 不进 |
| 附件上传里的父 item（仅 `items create --attach`：父 item 实际新建了）| ✅ 进 |
| 附件上传里的父 item（`items update --attach` / `items attach`：父 item 已存在，仅添加附件）| ❌ 不进（父 item 自身未变）|
| `collections add-items` / `collections remove-items` 命令 | **仅 collection key**（不含 item keys；语义="我修改了哪个 collection 的成员"）|
| `tags add` / `tags remove` 命令 | item keys（语义="哪些 item 的 tag 集发生了变化"）|
| `tags rename` / `tags delete` 命令 | 受影响的 item keys（语义同上；删除 tag 也是改 item）|

**示例**：WebDAV 后端下 `items attach --reuse-key` 重传，远端 md5 与本地一致（场景 B md5 检测命中、未带 `--force`），归入 `unchanged`。`--quiet` 模式下 stdout **完全为空**（0 字节、0 行，没有空白行也没有换行），退出码 0：
```bash
$ zotero-cli --quiet items attach ABC123XY paper.pdf --reuse-key ATT123XY | wc -c
0
$ zotero-cli --quiet items attach ABC123XY paper.pdf --reuse-key ATT123XY | wc -l
0
$ zotero-cli --quiet items attach ABC123XY paper.pdf --reuse-key ATT123XY ; echo "rc=$?"
rc=0
```
对比同命令带 `--force`（强制重传），stdout 输出 1 行 `attachment_key`，退出码 0：
```bash
$ zotero-cli --quiet items attach ABC123XY paper.pdf --reuse-key ATT123XY --force
ATT123XY
$ # ↑ 一行 attachment key + 一个换行符；wc -l 为 1
```

**实现约束**：`--quiet` 模式下 stdout 严格只输出 `affected_keys` 内容，每个 key 后跟一个 `\n`；`affected_keys` 为空时**不输出任何字节**（既不输出空行也不输出换行）。这样 `xargs -r`（GNU `--no-run-if-empty`）和 `[ -z "$(cmd)" ]` 都能正确判断"无 key"。

如果 agent 需要拿到所有"涉及"的 key（含 unchanged / failed），用 `--json` 解析完整 envelope，不要试图通过 `--quiet` + 后续推断重建。

### 7.3 格式定义

#### `kv-list`（列表，空行分隔）
```
key: ABC123XY
title: Attention is All You Need
creators: Vaswani, A.; Shazeer, N.
date: 2017-06
itemType: journalArticle
tags: transformer, nlp

key: DEF456WZ
title: BERT: Pre-training...
...
```

#### `kv`（单对象）
```
key: ABC123XY
title: Attention is All You Need
itemType: journalArticle
creators: Vaswani, A.; Shazeer, N.; Parmar, N.; ...
date: 2017-06
DOI: 10.48550/arXiv.1706.03762
abstractNote: ...
tags: transformer, nlp, attention
collections: PhD Papers, Deep Learning
```

#### `summary`（写操作结果）
```
✓ Created 2 items:
  ABC123XY, DEF456WZ

✗ 1 item failed:
  GHI789AB: Invalid item type "unknownType"
```

#### `tree`（层级数据）
```
PhD Papers [COLL123] (45 items)
├── 2024 Reading [COLL456] (12 items)
│   └── Transformers [COLL789] (8 items)
└── Archive [COLL234] (33 items)
```

#### `yaml`（配置显示）
```yaml
profile: default
api_key: abc1****xyz
library_id: 12345678
library_type: user
webdav:
  url: https://dav.example.com
  storage_path: /zotero
  username: myuser
  password: ****
```

#### `json`（全局 `--json`，envelope 详见 §8）

### 7.4 字段过滤

- `[<profile>.item_fields] list` 控制 items list/search 的默认字段
- `[<profile>.feed_item_fields] list` 控制 feeds items 的默认字段
- `--all-fields` 覆盖配置，显示全部字段
- `--json` 模式始终返回完整字段（忽略字段过滤）
- collections/tags 等不做字段过滤（总是全字段）

### 7.5 stdout/stderr 分离

- 数据走 stdout（可被管道捕获）
- 进度、警告、错误信息走 stderr
- `--json` 模式下 stdout 永远是合法 JSON（错误时也是合法 JSON envelope，包含 `ok=false` 和 error 对象，stdout 仍输出 JSON、stderr 不重复输出）
- 默认模式下错误走 stderr，stdout 保持空（便于脚本 `2>/dev/null` 静默错误）

---

## 8. JSON Envelope 规范

所有 `--json` 输出遵循统一结构：

```json
{
  "ok": <boolean>,
  "data": <any>,
  "error": <ErrorObject | null>,
  "meta": <MetaObject>
}
```

### 8.1 成功响应（列表）

```json
{
  "ok": true,
  "data": [
    {"key": "ABC123XY", ...}
  ],
  "error": null,
  "meta": {
    "command": "items.list",
    "elapsed_ms": 456,
    "library_id": "12345678",
    "library_type": "user",
    "profile": "default",
    "count": 2,
    "total": 247,
    "limit": 100,
    "start": 0,
    "next_start": 100,
    "library_version": 5678
  }
}
```

### 8.2 写操作响应

示例：批量 `items create` 提交了 4 个 item（index 0/1 成功创建，index 2 因字段值未变化被服务端归为 unchanged，index 3 因无效 type 失败）。`affected_keys` 仅包含 successful 项（unchanged / failed 不进，规则见 §7.2.1）。

```json
{
  "ok": true,
  "data": {
    "successful": [
      {"index": 0, "key": "ABC123XY", "version": 5679, "data": {...}},
      {"index": 1, "key": "DEF456WZ", "version": 5680, "data": {...}}
    ],
    "unchanged": [
      {"index": 2, "key": "GHI789AB"}
    ],
    "failed": [
      {
        "index": 3,
        "code": "INVALID_ITEM_TYPE",
        "message": "Invalid item type: unknownType",
        "context": {"itemType": "unknownType"}
      }
    ]
  },
  "error": null,
  "meta": {
    "command": "items.create",
    "elapsed_ms": 1234,
    "affected_keys": ["ABC123XY", "DEF456WZ"]
  }
}
```

### 8.3 附件上传响应

`data` schema 与后端无关，外层结构固定；条目内字段按 backend 区分。pyzotero 的 `success/failure/unchanged` 三态在 ZFS 路径下原样保留（`unchanged` 表示远端 md5 已一致，未发生网络上传）。WebDAV 路径只产 `uploaded` 或 `failed` 两类（自实现协议下我们主动上传，没有 `unchanged` 概念；除非 §10.5 场景 B 的 md5 检测命中——此时归为 `unchanged`）。

#### Schema 稳定性约定

**字段总存在原则**（适用范围：`uploaded[]` 和 `unchanged[]` 条目；`failed[]` 用独立的错误对象 schema，见 §8.3 末尾"`failed[]` 独立 schema"段）：每个成功或未变上传条目的 schema 在 ZFS 与 WebDAV 后端下**字段集合完全一致**，后端不适用的字段输出为 `null`（不省略 key）。这样 agent / jq 解析器无需做 `has("webdav_path")` 这类条件判断，可以直接 `.uploaded[].webdav_path // empty` 统一处理。

```json
{
  "ok": true,
  "data": {
    "backend": "zfs",                     // "zfs" | "webdav"，由 _select_backend(profile) 决定
    "uploaded": [
      {
        "file": "paper.pdf",
        "attachment_key": "ATT123XY",
        "parent_item_key": "ABC123XY",
        "size_bytes": 2411520,
        "md5": "d41d8cd98f00b204e9800998ecf8427e",
        // ZFS 字段（WebDAV 后端下为 null）
        "version": 5681,
        // WebDAV 字段（ZFS 后端下为 null）
        "webdav_path": null,
        "mtime_ms": null
      }
    ],
    "unchanged": [
      // 远端 md5 已一致、无实际上传的条目（条目结构与 uploaded[] 完全一致；后端不适用字段为 null）
    ],
    "failed": [
      // 未抛异常但被服务端/协议拒绝的条目（独立的错误对象 schema，见 §8.3 末尾说明）
      {
        "file": "broken.pdf",
        "attachment_key": null,           // 还没创建出 key 时为 null（fail 在 _create_prelim 阶段）
        "parent_item_key": "ABC123XY",
        "code": "STORAGE_QUOTA_EXCEEDED",
        "message": "Upload would exceed Zotero File Storage quota",
        "context": {"size_bytes": 524288000, "limit_bytes": 524288000}
      }
    ]
  },
  "error": null,
  "meta": {
    "command": "items.attach",
    "elapsed_ms": 5678,
    "backend": "zfs",                     // 与 data.backend 同步，便于在不读 data 时筛选日志
    "affected_keys": ["ATT123XY"]         // 见 §8.3.1 affected_keys 计算规则
  }
}
```

**片段示例**（WebDAV 后端，仅展示 `data` 部分以突出后端差异字段；完整 envelope 结构与上方 ZFS 示例一致，含 `ok` / `data` / `error` / `meta` 四个顶层 key——勿照抄此片段为测试 fixture）：
```json
// 仅 data 片段，非完整响应
{
  "data": {
    "backend": "webdav",
    "uploaded": [
      {
        "file": "paper.pdf",
        "attachment_key": "ATT123XY",
        "parent_item_key": "ABC123XY",
        "size_bytes": 2411520,
        "md5": "d41d8cd98f00b204e9800998ecf8427e",
        "version": null,                  // ZFS 字段在 WebDAV 后端为 null
        "webdav_path": "/zotero/ATT123XY.zip",
        "mtime_ms": 1717584321000
      }
    ],
    "unchanged": [],
    "failed": []
  }
}
```

**字段表**（统一 schema，所有字段在 ZFS / WebDAV 两后端下都出现）：

| 字段 | 类型 | ZFS 取值来源 | WebDAV 取值来源 | 备注 |
|---|---|---|---|---|
| `backend` | str | `"zfs"` | `"webdav"` | `_select_backend(profile)` 输出 |
| `uploaded[].file` | str | 用户传入路径（basename） | 同 | 原路径在审计日志保留 |
| `uploaded[].attachment_key` | str | pyzotero 返回 `key` | CLI 自己创建后获得 | `--reuse-key` 场景下等于传入值 |
| `uploaded[].parent_item_key` | str | pyzotero 返回 `parentItem` | CLI 已知父 key | |
| `uploaded[].size_bytes` | int | pyzotero 返回 `filesize` | 本地文件 stat | |
| `uploaded[].md5` | str | pyzotero 返回 `md5` | 本地计算 | |
| `uploaded[].version` | int \| null | pyzotero 返回 `version` | **null**（WebDAV 后端不适用） | ZFS 专属 |
| `uploaded[].webdav_path` | str \| null | **null**（ZFS 后端不适用） | `<storage_path>/<key>.zip` | WebDAV 专属 |
| `uploaded[].mtime_ms` | int \| null | **null**（ZFS 后端不适用） | 写入 prop 的时间戳 | WebDAV 专属 |
| `unchanged[]` | object | pyzotero 返回 | WebDAV 场景 B 检测 | **结构与 `uploaded[]` 完全一致**；不视为错误，退出码 0 |
| `failed[]` | object | 错误对象，独立 schema（见下） | 同 | 不沿用 `uploaded[]` 字段集 |

**`failed[]` 独立 schema**（与 `uploaded[]` / `unchanged[]` 故意不同）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `file` | str | 用户传入路径（basename），固定存在 |
| `attachment_key` | str \| null | 失败若发生在 attachment item 已创建之后（如 WebDAV 路径下 zip 上传失败），为该 key；若发生在创建之前（如本地文件不存在、`_create_prelim` 阶段失败），为 `null` |
| `parent_item_key` | str | 父 item key，固定存在（attach 命令的输入参数已知） |
| `code` | str | CLI 错误码（与 §9.2 对齐；ZFS 后端来自 §10.0.2.6 翻译表，WebDAV 后端来自 §10.0.4） |
| `message` | str | 人类可读错误描述 |
| `context` | object \| null | 错误相关上下文（如 quota 信息、HTTP 状态码、底层异常类名等），可选 |

**为何不沿用 `uploaded[]` schema**：失败条目缺乏可信的 `size_bytes` / `md5` / `version` / `webdav_path` / `mtime_ms`（计算 md5 前文件可能就读失败；attachment_key 还没存在时 webdav_path 也无法生成）。强行填 null 反而让 agent 误以为这些字段在 failed 上下文里有意义。`failed[]` 与 envelope 顶层 `error` 对象（§8.5）共享 `code` / `message` / `context` 三元组，agent 可以用同一套错误处理代码消费两处。

#### 8.3.1 `affected_keys` 计算规则（关键 agent 契约）

`meta.affected_keys` **只列实际产生服务端状态变更的 key**（包括父 item 与 attachment item）：

| 来源 | 是否进 `affected_keys` |
|---|---|
| 新创建的父 item key（`items create --attach`）| ✅ 进 |
| 新创建的 attachment item key（来自 `data.uploaded[]`）| ✅ 进 |
| `--reuse-key` 场景下重传成功的 attachment key（`data.uploaded[]`）| ✅ 进 |
| `data.unchanged[]` 里的 attachment key | ❌ 不进（未发生变更）|
| `data.failed[]` 里的 attachment key（如有）| ❌ 不进 |

`--quiet` 模式输出严格等于 `meta.affected_keys`（每行一个，与 §7.2 一致），保证 `xargs` 管道下游接到的全部是"真正改过的 key"，不会误清理 `unchanged` 项。

详见 §7.2 的 `--quiet` 规范扩展说明。

### 8.4 Dry-run 响应

```json
{
  "ok": true,
  "data": {
    "dry_run": true,
    "would_create": [...],
    "would_upload": [...]
  },
  "error": null,
  "meta": {"command": "items.create", "dry_run": true}
}
```

### 8.5 错误响应

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "ITEM_NOT_FOUND",
    "message": "Item with key 'ABC123XY' does not exist in library 12345678",
    "category": "user_error",
    "hint": "Use 'zotero-cli items list' to see available items",
    "context": {"item_key": "ABC123XY", "library_id": "12345678"},
    "cause": null
  },
  "meta": {
    "command": "items.show",
    "elapsed_ms": 123,
    "exit_code": 1
  }
}
```

---

## 9. 错误码与退出码

### 9.1 退出码表

| 退出码 | 类别 | 含义 |
|---|---|---|
| `0` | 成功 | |
| `1` | user_error | 用户输入错误（资源不存在、参数无效） |
| `2` | network_error | API/网络错误 |
| `3` | auth_error | 认证失败 |
| `4` | local_error | 本地数据错误（SQLite、配置、文件系统） |
| `64` | usage_error | 命令行用法错误 |
| `130` | interrupted | 用户中断（Ctrl+C） |

### 9.2 错误码（精选）

**用户输入错误（1）**：`ITEM_NOT_FOUND`、`COLLECTION_NOT_FOUND`、`TAG_NOT_FOUND`、`FEED_NOT_FOUND`、`INVALID_ITEM_TYPE`、`INVALID_DATE_FORMAT`、`INVALID_FIELD`、`MISSING_REQUIRED_ARG`、`FILE_NOT_FOUND`、`INVALID_PROFILE`、`UNSUPPORTED_LIBRARY_TYPE`（`library_type=group` 配了 `[webdav]`，见 §10.0.1）

**网络错误（2）**：`API_TIMEOUT`、`API_RATE_LIMIT`、`API_SERVER_ERROR`、`WEBDAV_TIMEOUT`、`WEBDAV_CONNECTION_ERROR`、`NETWORK_ERROR`

**认证错误（3）**：`INVALID_API_KEY`、`INSUFFICIENT_PERMISSIONS`、`WEBDAV_AUTH_FAILED`

**本地错误（4）**：`SQLITE_NOT_FOUND`、`SQLITE_LOCKED`、`SQLITE_SCHEMA_INCOMPATIBLE`、`CONFIG_NOT_FOUND`、`CONFIG_INVALID`、`AUDIT_LOG_WRITE_FAILED`、`WEBDAV_FILE_EXISTS`、`MD5_MISMATCH`、`WEBDAV_PROP_INVALID`（WebDAV 后端读到的 `.prop` XML 结构非法/字段缺失/编码错误，§10.2 Step 4a 解析失败）

**存储/配额错误（2，与 network_error 同退出码）**：`STORAGE_QUOTA_EXCEEDED`（统一名，触发条件按后端区分）。详细映射见下表。

| 后端 | 触发条件 | CLI 错误码 | category | 退出码 |
|---|---|---|---|---|
| ZFS | pyzotero 抛 `RequestEntityTooLargeError`（HTTP 413，超 Zotero File Storage 配额） | `STORAGE_QUOTA_EXCEEDED` | network_error | 2 |
| WebDAV | PUT zip / prop 时收到 507 Insufficient Storage 或 413 Payload Too Large | `STORAGE_QUOTA_EXCEEDED` | network_error | 2 |

**用法错误（64）**：`USAGE_ERROR`、`MUTUALLY_EXCLUSIVE_ARGS`

### 9.3 默认模式错误展示

```
$ zotero-cli items show NOTEXIST
✗ Error: ITEM_NOT_FOUND
  Item with key 'NOTEXIST' does not exist in library 12345678

  Hint: Use 'zotero-cli items list' to see available items.

$ echo $?
1
```

### 9.4 审计日志

`~/.local/state/zotero-cli/audit.log`（JSONL 格式）：

```json
{"timestamp":"2026-06-07T14:23:45Z","profile":"default","command":"items.create","args":{...},"result":"success","affected_keys":["ABC123XY"],"elapsed_ms":234}
```

策略：
- 只记录写操作（create/update/delete/attach）
- 不记录敏感信息（密码、完整 API key 仅保留前 4 位）
- 失败也记录
- 单文件超过 10MB 自动压缩归档为 `audit.log.YYYY-MM.gz`

---

## 10. 附件上传：ZFS（默认）与 WebDAV（可选）

### 10.0 后端选择策略与适用范围

CLI 的附件上传有两条后端路径，按 profile 配置自动选择：

| 后端 | 触发条件 | 实现 | 协议确定性 | 适用 library |
|---|---|---|---|---|
| **A. Zotero File Storage（ZFS，默认）** | profile 中**没有** `[<profile>.webdav]` 段 | pyzotero 的 `attachment_simple()` / `attachment_both()` / `upload_attachments()` / `Zupload` | 完全官方，pyzotero 已实现 | personal + group 都支持 |
| **B. 自实现 WebDAV 协议** | profile 中**有** `[<profile>.webdav]` 段 | 本 CLI 的 `adapters/webdav_client.py`（zip + prop） | 协议待实测确认（见 §10.1） | **仅 personal**（Zotero 官方 WebDAV 不支持 group） |

**配置入口判定**（在 `adapters/zotero_api.py` 的 attachment 派发层做）：
```python
def _select_backend(profile: ProfileConfig) -> Literal["zfs", "webdav"]:
    return "webdav" if profile.webdav is not None else "zfs"
```

不在命令行暴露后端切换 flag——切换就改 config 或换 profile，避免单次调用错配。

### 10.0.1 后端 × library 兼容性矩阵

| 配置 | 上传行为 |
|---|---|
| `library_type=user`，无 `[webdav]` | ✅ 走 ZFS（pyzotero） |
| `library_type=user`，有 `[webdav]` | ✅ 走自实现 WebDAV |
| `library_type=group`，无 `[webdav]` | ✅ 走 ZFS（pyzotero）|
| `library_type=group`，有 `[webdav]` | ❌ `config validate` 报 `UNSUPPORTED_LIBRARY_TYPE`；attach 操作直接拒绝（Zotero 官方 WebDAV 不支持 group library） |

**前置校验位置**：
- `commands/config.py validate`：检查上述兼容性
- `services/attachment_service.py` 入口第 0 步：再次确认（防止 config 绕过）

### 10.0.2 ZFS 路径（后端 A）实现要点

ZFS 路径几乎全部委托给 pyzotero，本 CLI 只做：参数翻译、返回值映射、审计日志、失败回滚。

#### 10.0.2.1 pyzotero 附件 API 能力（待 spike 验证的假设）

下表基于 pyzotero 1.5+ 公开文档整理，**未在本项目内做端到端实测**。阶段 3 spike（见 §13）必须用真实账号验证下表每一行；任何与表格不符的发现都要回头修订本节再继续实现。

| pyzotero API | 输入 | 行为 | `parentid` 兼容 existing key？ |
|---|---|---|---|
| `attachment_simple(files, parentid=None)` | `list[str]` 文件路径 | 创建 attachment item + 上传，文件名作 title | N/A（总是新建） |
| `attachment_both(files, parentid=None)` | `list[(title, filepath)]` | 同上，custom title | N/A（总是新建） |
| `upload_attachments(attachments, parentid=None, basedir=None)` | `list[dict]`（来自 `item_template('attachment','imported_file')`，可带 `key` 字段） | 若 dict 无 `key` 则新建；有 `key` 则视为已存在的 attachment item，仅上传文件 | ❌ 与 existing key 不兼容（pyzotero 文档明确） |
| `Zupload(zinstance, payload, parentid=None, basedir=None).upload()` | 同上 | 完整 4 步：`_create_prelim` → `_get_auth` → `_upload_file` → `_register_upload`；md5 匹配则归入 `unchanged` | ❌ 同 `upload_attachments` |

**返回值统一形态**：所有上述方法返回 `UploadResult = TypedDict({success, failure, unchanged}, list[dict])`。

**不在本 CLI 范围内**：pyzotero 提供的 `dump(item_key, path)` 文件下载方法本设计未启用——下载附件不在功能范围（§2）；如未来要加再单独设计 `items dump` 命令、确定输出格式（kv / json）和 progress 行为。

**`unchanged` 含义（重要）**：服务器端 md5 与本地文件一致，pyzotero **完全跳过 `_get_auth` + `_upload_file`**，不会重新上传。这是 ZFS 协议的幂等性。

#### 10.0.2.2 CLI 命令到 pyzotero API 的映射

| CLI 命令 | pyzotero 调用 | 关键参数 |
|---|---|---|
| `items create --attach <file.pdf> [--attach-title <t>]` | 1) `create_items([item_template])` 创建父 item → 拿 `parent_key`；2) `attachment_both([(att_title, file)], parentid=parent_key)`，未提供 `--attach-title` 时直接用 `attachment_simple([file], parentid=parent_key)`（pyzotero 内部以文件名为 title）| `--title` 永远是父 item 标题；附件 title 走独立的 `--attach-title` |
| `items update <key> --attach <file.pdf> [--attach-title <t>]` | 同上，`parentid=<key>`，`--attach-title` 缺省时走 `attachment_simple` | 父 item 已存在 |
| `items attach <parent-key> <file.pdf>`（无 `--reuse-key`）| 有 `--title` 走 `attachment_both([(<title>, file)], parentid=<parent-key>)`；无则 `attachment_simple([file], parentid=<parent-key>)` | `items attach` 自身的 `--title` 就是附件标题（无父 item 标题歧义） |
| `items attach <parent-key> <file.pdf> --reuse-key <att-key>` | `upload_attachments([template_with_key], parentid=None, basedir=None)`，其中 `template_with_key['key']=<att-key>` 且 `template_with_key['filename']=<file>` | **`parentid` 必须为 None**（pyzotero 限制） |

#### 10.0.2.3 ZFS 路径下 `--force` 禁用

**结论**：ZFS 路径下**禁止 `--force`**，传入直接报 `MUTUALLY_EXCLUSIVE_ARGS`（退出码 64），错误消息：
```
--force is only supported with WebDAV backend (config has [<profile>.webdav]).
ZFS backend uses md5-based idempotency; pyzotero does not expose force-overwrite.
To re-upload a file under existing attachment key, you must first manually clear
the server-side file (delete + recreate the attachment item, or change md5 metadata).
```

理由：pyzotero 对 `unchanged`（远端 md5 一致）**没有公开 API 强制重传**，给用户/agent 一个会被静默忽略的 flag 比直接拒绝更糟糕。如果用户真的需要在 ZFS 下"强制重传"，明确的 workaround 是：
```bash
# 用户自己处理 workaround（不在 CLI 内置）
zotero-cli items delete <attachment-key>           # 删除旧 attachment
zotero-cli items attach <parent-key> <file.pdf>    # 重新创建 + 上传
```
不在 CLI 内自动做这件事，因为"删除并重建"会改变 attachment key（其他引用会失效），后果应由用户显式承担。

#### 10.0.2.4 ZFS 路径下 `--reuse-key`

ZFS 路径下 `--reuse-key` 走 `upload_attachments`，对应 pyzotero 文档"resuming interrupted syncs"场景。

**约束**：
- 对应的 attachment item 必须已经存在（CLI 调用前应当先 `zot.item(att_key)` 探活，404 则返回 `ITEM_NOT_FOUND`）
- `parentid` 参数必须为 None（pyzotero 不兼容）；attachment item 的 parent 关系已经在它自身的 `parentItem` 字段里
- 若 pyzotero 返回 `unchanged`（远端 md5 一致），CLI 在 envelope 里如实返回（`data.uploaded=[]`、`data.unchanged=[...]`），不视为错误，退出码 0

#### 10.0.2.5 ZFS 路径失败回滚

| 失败位置 | 回滚动作 |
|---|---|
| **A1. `items create --attach`：父 item 创建失败** | 无副作用，直接报错退出 |
| **A2. `items create --attach`：父 item 创建成功但 `attachment_both` 整体抛异常**（`UploadError` / `TooManyRequestsError` / `RequestEntityTooLargeError`） | **不自动回滚父 item**；envelope 中明确返回 `parent_created=true`、`attachment_uploaded=false` 和父 item key，让用户/agent 决定保留还是清理。理由：pyzotero 异常发生时，部分 attachment 子项可能已部分上传（`success` / `failure` 混合），自动删父 item 会连带删掉已经成功的 attachment，破坏其他正在进行的写操作 |
| **A3. `items create --attach`：父 item 创建成功，但 pyzotero 返回 `failure` 非空（无异常）** | 同 A2：保留父 item，envelope 中 `failed[]` 列出失败附件；用户可后续 `items attach` 重试 |
| **B1. `items update --attach`：`attachment_both` 抛异常** | 无父 item 操作，envelope 返回错误，退出码 2 / 3 / 4（按错误类型映射） |
| **B2. `items update --attach`：pyzotero 返回 `failure` 非空** | envelope 返回 `failed[]`，退出码取决于是否全失败：全失败退 2，部分失败退 0（success 非空时） |
| **C. `items attach`（独立命令）失败** | 同 B（无父 item 改动） |

**与 WebDAV 路径回滚（§10.4）的关键差异**：
- WebDAV 路径自己创建/删除 attachment item，可以做"创建失败 → 回滚 attachment item"
- ZFS 路径让 pyzotero 一次完成"创建 attachment item + 上传文件"两步，CLI 没有插入回滚的时机
- 因此 ZFS 路径采用"前向修复"策略：失败时返回足够信息让用户/agent 后续修复

#### 10.0.2.6 错误码映射（pyzotero 异常 → CLI 错误码）

| pyzotero 异常 | CLI 错误码 | 退出码类别 |
|---|---|---|
| `FileDoesNotExistError` | `FILE_NOT_FOUND` | user_error (1) |
| `ParamNotPassedError` | `MISSING_REQUIRED_ARG` | usage_error (64) |
| `UnsupportedParamsError` | `MUTUALLY_EXCLUSIVE_ARGS` | usage_error (64) |
| `TooManyRequestsError` | `API_RATE_LIMIT` | network_error (2) |
| `RequestEntityTooLargeError` | `STORAGE_QUOTA_EXCEEDED`（与 WebDAV 后端统一） | network_error (2) |
| `PreConditionFailedError` | `API_SERVER_ERROR` | network_error (2) |
| `UploadError`（含网络/超时） | `API_TIMEOUT` 或 `NETWORK_ERROR`（按底层异常类型再分） | network_error (2) |
| 401/403（zotero_errors.UserNotAuthorisedError 等） | `INVALID_API_KEY` / `INSUFFICIENT_PERMISSIONS` | auth_error (3) |

### 10.0.3 WebDAV 路径（后端 B）实现要点

WebDAV 路径是本 CLI 自己实现的，§10.1–10.6 全部针对此路径。简要：
- 必须 `library_type = "user"`，否则 `UNSUPPORTED_LIBRARY_TYPE`
- 用 `webdav4.Client` 走 PROPFIND/MKCOL/PUT/DELETE
- 自己计算 md5、构造 zip（base64 编码内部文件名、`ZIP_STORED` 不压缩）、构造 prop XML
- 上传后用 pyzotero PATCH attachment item 的 `md5` + `mtime` 字段（这是 Zotero file_upload 文档明确允许的：`md5`/`mtime` 在 personal library + WebDAV 模式下可直接编辑）
- `--reuse-key` 走 §10.5 场景 B，`--force` 跳过远端 md5 检测

### 10.0.4 错误码区分

| 错误码 | 触发条件 |
|---|---|
| `UNSUPPORTED_LIBRARY_TYPE` | `library_type=group` 且配了 `[webdav]`（互斥） |
| `WEBDAV_AUTH_FAILED` | WebDAV 路径下 401/403 |
| `WEBDAV_CONNECTION_ERROR` / `WEBDAV_TIMEOUT` | WebDAV 路径下网络问题 |
| `STORAGE_QUOTA_EXCEEDED` | ZFS 路径下 pyzotero 抛 `RequestEntityTooLargeError`（HTTP 413）；WebDAV 路径下 PUT 收到 507 Insufficient Storage 或 413 Payload Too Large。两后端共用同一错误码（详见 §9.2 存储/配额错误段） |
| `API_*`（来自 pyzotero） | ZFS 路径下的网络/认证错误（由 adapter 层翻译，详见 §10.0.2.6） |

注：移除上一版本里的 `WEBDAV_CONFIG_MISSING`——既然 ZFS 是默认 fallback，"没配 WebDAV" 不再是错误。

参考来源：
- Zotero file_upload 文档：`md5`/`mtime`/`filename`/`contentType`/`charset` 仅 personal library + WebDAV 模式下可直接编辑
- Zotero forums [WebDAV sync for group libraries](https://forums.zotero.org/discussion/77589/webdav-sync-for-group-libraries)：明确说明 group 不支持 WebDAV 的设计原因

---

### 10.1 Zotero WebDAV 协议（待实测确认的协议假设）

> **作用域**：本节及 §10.2–10.6 全部仅适用于后端 B（WebDAV 路径）。后端 A（ZFS）走 pyzotero 内建实现，与下文协议细节无关。

以下协议描述基于源码逆向 + 社区文档整理，**不是 Zotero 官方公开规范**。实施前必须按 §10.6 风险点逐项实测验证；任何字节级不一致都会让 Zotero 桌面端把上传文件视为"被外部修改"并触发重传。

**服务器布局**（以 `url=https://dav.example.com` + `storage_path=/zotero` 为例，`storage_path` 默认 `/zotero`，可改为 `""`（根目录）或其他路径以适配特定 WebDAV 服务）：
```
https://dav.example.com/zotero/    ← url + storage_path
├── lastsync                  ← 同步标记
├── ABC123XY.zip              ← 附件 zip（itemKey 命名）
├── ABC123XY.prop             ← 元数据 XML
└── ...
```

实现要点：
- `webdav4.Client(base_url=url, ...)` 用 `url`（不含 storage_path）
- **`storage_path` normalize 规则**（在 `pydantic` validator 里执行，校验失败抛 `CONFIG_INVALID`）：
  - 空字符串 `""` 合法（直接放服务器根目录）
  - 非空字符串必须以 `/` 开头，且**不能以 `/` 结尾**（normalize 时自动 strip 尾部 `/`，所以用户写 `/zotero/` 也会被规范成 `/zotero`）
  - 不允许只有 `/`（应改用 `""`）
  - 不允许包含 `..` 或连续 `//`
- 所有 WebDAV 调用拼接路径 = `f"{storage_path}/{key}.zip"`（normalize 后 storage_path 末尾无 `/`，拼接结果首字符必为 `/`）
- `storage_path = ""` 时拼接结果就是 `f"/{key}.zip"`

**zip 内部结构**：内含 PDF，文件名是原始文件名的 base64 编码。

**.prop XML 格式**（与 Zotero 客户端字节级一致）：
```xml
<properties version="1"><mtime>1717584321000</mtime><hash>d41d8cd98f00b204e9800998ecf8427e</hash></properties>
```

字段：
- `mtime`：毫秒级 Unix 时间戳（整数）
- `hash`：PDF 文件的 MD5 hex（32 字符小写）
- `version="1"`：固定属性

**HTTP 方法**：`PROPFIND`、`MKCOL`、`PUT`、`DELETE`、`GET`

### 10.2 完整上传流程（6 步，仅 WebDAV 后端）

> 进入本流程的前提：`_select_backend()` 已返回 `"webdav"`（即 profile 配了 `[webdav]` 段且 `library_type=user`）。
> 否则走 §10.0.2 的 ZFS 路径，与本节无关。

0. **前置校验**：再次确认 `library_type == "user"`（防御 config 绕过），不通过则报 `UNSUPPORTED_LIBRARY_TYPE`
1. **验证**：检查 PDF 存在、父条目存在
2. **创建 attachment item**（pyzotero）：`linkMode=imported_file`，md5/mtime 暂为 None，拿到 attachment key
3. **准备 WebDAV 上传**：计算 md5、读取 mtime、构造 zip（base64 编码内部文件名，`ZIP_STORED` 不压缩）、构造 prop XML
4. **WebDAV 上传**（路径 = `storage_path + /<key>.{zip,prop}`，下文以 `storage_path=/zotero` 为例）：
   - 4a. PROPFIND `<storage_path>/` → 不存在则 MKCOL（`storage_path=""` 时跳过此步）
   - 4b. PUT `<storage_path>/<key>.zip`
   - 4c. DELETE `<storage_path>/<key>.prop`（404 忽略）
   - 4d. PUT `<storage_path>/<key>.prop`
5. **更新 attachment 元数据**（pyzotero PATCH）：写入 md5 + mtime
   - **直接编辑 md5/mtime 仅在 personal library + WebDAV 模式下安全**（已由 Step 0 保证）
   - 若 Step 0 校验绕过（不应发生），Zotero API 会返回 400/403，错误归类为 `INSUFFICIENT_PERMISSIONS`
6. **审计日志 + 返回结果**

### 10.3 WebDAV 失败回滚

| 失败位置 | 回滚动作 |
|---|---|
| Step 2（创建 item 失败） | 直接报错退出 |
| Step 4b（zip 上传失败） | 删除 Step 2 的 attachment item |
| Step 4d（prop 上传失败） | 删除 zip + 删除 attachment item |
| Step 5（更新 md5/mtime 失败） | 不回滚（zip 已上传，下次重试只更新元数据） |

### 10.4 WebDAV 批量上传策略

仅在**单次命令上传 ≥2 个文件**时启用并发（如 `items create --json-file` 含多个附件），单文件上传走串行路径不开线程池。

- 串行调用 pyzotero 创建 attachment items（API 速率限制）
- 并发上传 zip + prop（最多 4 并发，与 Zotero API 限制一致）
- 串行更新 md5/mtime（pyzotero 批量更新，每批 50 个）
- 用 `concurrent.futures.ThreadPoolExecutor(max_workers=4)` 实现（webdav4 是同步 API）

### 10.5 WebDAV 重复检测与 `--force` 的语义

> **作用域**：本节仅描述 WebDAV 后端的 `--force` 语义。ZFS 后端**禁止 `--force`**，详见 §10.0.2.3。

**两类场景区分**：

| 场景 | 是否会触发"已存在"检测 | `--force` 的作用 |
|---|---|---|
| **A. 新建 attachment**（`items create --attach` / `items attach <parent> <file>`（不带 `--reuse-key`）/ `items update --attach`）| ❌ 不触发：每次新建都会拿到全新 attachment key，远端按 key 命名所以必然不存在 | 这些场景**不接受** `--force` 参数（仅 `items attach --reuse-key` 接受） |
| **B. 重试已有 attachment 的上传**（`items attach --reuse-key <existing-key>`，attachment item 已存在但 WebDAV 上传/元数据更新中断）| ✅ 触发：检查远端 `<storage_path>/<key>.prop` 中的 md5 与本地 PDF md5 是否一致 | 强制重新上传 zip + prop（即便 md5 一致） |

**场景 B 触发**：仅通过 `items attach --reuse-key <existing-attachment-key> <file>` 进入。`items create --attach` 和 `items update --attach` 的语义就是"为这个 item 新增一个 attachment"，不复用 key。

**重复检测实现**（仅场景 B 用）：

```python
def needs_reupload(attachment_key, local_md5, webdav_client, storage_path):
    """场景 B：基于 attachment_key 检查远端 .prop 中的 md5"""
    prop_path = f"{storage_path}/{attachment_key}.prop"
    if not webdav_client.exists(prop_path):
        return True  # 远端无 prop，需上传
    remote_md5 = parse_prop(webdav_client.download(prop_path)).hash
    return remote_md5 != local_md5
```

**关于"按文件 hash 防重"的取舍**：本设计**不实现**"同一父 item 下检测重复 PDF"，原因：
- Zotero 桌面端本身允许同一父 item 下挂多个同 hash 的 PDF（用户偏好）
- 实现成本（要拉父 item 的所有 children + 查 md5 + 处理无 md5 的旧 attachment）和收益不匹配
- 用户若需要去重，可在调用 CLI 前自行 `dedupe`

**命令树调整**：`items attach` 增加 `--reuse-key` 选项

### 10.6 WebDAV 实现风险点（plan 阶段必须验证）

| 风险点 | 验证方式 |
|---|---|
| **base64 编码方式**（标准 vs 修改版） | 用 Zotero 客户端实际上传一个 PDF，下载 zip 检查内部文件名 |
| **mtime 一致性** | 上传后用 Zotero 桌面端打开，确认不触发"重新同步" |
| **prop XML 精确格式**（空格、换行、属性顺序） | 抓取真实 prop 文件对照 |
| **`storage_path` 默认值** | 默认 `/zotero`；空字符串 `""` 表示直接放服务器根目录（适配某些受限 WebDAV）；用户可在 config 中改 |

---

## 11. SQLite 只读访问（RSS）

### 11.1 访问策略

**直接只读连接**（不复制到 tmp）：

```python
uri = f"file:{sqlite_path}?mode=ro&nolock=1"
conn = sqlite3.connect(uri, uri=True, timeout=5.0)
```

- `mode=ro`：只读，禁止误写
- `nolock=1`：不获取文件锁，与 Zotero 桌面端的写入并存
- 最坏情况：读到"差几秒"的数据，对 RSS 浏览完全可接受
- 不会损坏数据库

### 11.2 关键发现：Zotero multipart date 格式

**`feed_id` 约定**：本设计中所有命令和输出字段里的 `feed_id` 都对应 SQLite `feeds.libraryID`（整数）。`feeds list` 默认输出第一列就是 `feed_id`，方便用户复制后传给 `feeds show <feed-id>` / `feeds items <feed-id>`。`FeedItem` 模型里也带 `feed_id` 字段（来自 `items.libraryID`），便于 `--json` 模式跨 feed 关联。

Zotero 在 `itemDataValues.value` 存储 date 字段时使用 multipart 格式：

```
YYYY-MM-DD <原始字符串>
```

缺失部分用 `00` 占位：

| 用户输入 | 存储值 |
|---|---|
| `2017-06-15` | `2017-06-15 2017-06-15` |
| `2017-06` | `2017-06-00 2017-06` |
| `2017` | `2017-00-00 2017` |
| `June 2017` | `2017-06-00 June 2017` |
| `Summer 2006` | `2006-00-00 Summer 2006` |
| `March 15, 2024` | `2024-03-15 March 15, 2024` |

**关键结论**：前 10 字符**总是** `YYYY-MM-DD` 形式，可以直接在 SQL 中用字符串比较完成 date 过滤，不需要 Python 端二次过滤。

### 11.3 SQL 查询（LEFT JOIN + SQL date 过滤）

#### 11.3.1 列出所有 feeds

```sql
SELECT
    f.libraryID,
    f.name,
    f.url,
    f.lastUpdate,
    f.lastCheck,
    f.lastCheckError,
    f.refreshInterval,
    COUNT(fi.itemID) AS total_count,
    SUM(CASE WHEN fi.readTime IS NULL THEN 1 ELSE 0 END) AS unread_count
FROM feeds f
LEFT JOIN items i ON i.libraryID = f.libraryID
LEFT JOIN feedItems fi ON fi.itemID = i.itemID
GROUP BY f.libraryID
ORDER BY f.name;
```

#### 11.3.2 查询 feed items（LEFT JOIN + SQL 过滤）

```sql
-- 启动时缓存字段 ID
SELECT fieldID, fieldName FROM fields
WHERE fieldName IN ('title', 'date', 'url', 'abstractNote');

-- 实际查询
SELECT
    fi.itemID,
    fi.guid,
    fi.readTime,
    fi.translatedTime,
    i.dateAdded,
    i.dateModified,
    title_v.value     AS title,
    date_v.value      AS date_raw,
    SUBSTR(date_v.value, 1, 10) AS date_sql,
    url_v.value       AS url,
    abstract_v.value  AS abstract
FROM feedItems fi
JOIN items i ON i.itemID = fi.itemID
LEFT JOIN itemData title_id ON title_id.itemID = i.itemID AND title_id.fieldID = ?
LEFT JOIN itemDataValues title_v ON title_v.valueID = title_id.valueID
LEFT JOIN itemData date_id ON date_id.itemID = i.itemID AND date_id.fieldID = ?
LEFT JOIN itemDataValues date_v ON date_v.valueID = date_id.valueID
LEFT JOIN itemData url_id ON url_id.itemID = i.itemID AND url_id.fieldID = ?
LEFT JOIN itemDataValues url_v ON url_v.valueID = url_id.valueID
LEFT JOIN itemData abstract_id ON abstract_id.itemID = i.itemID AND abstract_id.fieldID = ?
LEFT JOIN itemDataValues abstract_v ON abstract_v.valueID = abstract_id.valueID
WHERE i.libraryID = ?
  AND (
    -- include_undated 由调用方传入布尔值（0 或 1），SQL 端做参数化判断
    -- 默认 0（排除）→ 整个 OR 左侧短路为 false，只保留有日期且在范围内的
    -- 设为 1（包含）→ NULL 也匹配
    (? = 1 AND date_v.value IS NULL)
    OR (
      date_v.value IS NOT NULL
      AND SUBSTR(date_v.value, 1, 10) >= ?  -- start
      AND SUBSTR(date_v.value, 1, 10) <= ?  -- end
    )
  )
ORDER BY SUBSTR(date_v.value, 1, 10) DESC NULLS LAST
LIMIT ?;
```

**绑定参数顺序**（4 个 fieldID + libraryID + include_undated_int + start + end + limit）：
- 4 个字段 ID（title、date、url、abstractNote）
- libraryID
- `1 if include_undated else 0`
- date_start（如 `"2024-00-00"`）
- date_end（如 `"2024-12-31"`）
- limit

#### 11.3.3 Creators 查询（独立 IN 子句）

```sql
SELECT ic.itemID, c.firstName, c.lastName, c.fieldMode,
       ct.creatorType, ic.orderIndex
FROM itemCreators ic
JOIN creators c ON c.creatorID = ic.creatorID
JOIN creatorTypes ct ON ct.creatorTypeID = ic.creatorTypeID
WHERE ic.itemID IN (...)
ORDER BY ic.itemID, ic.orderIndex;
```

### 11.4 date 参数 → SQL 边界

支持的语法：单日 / 范围 / 开区间 / 年 / 年-月（不支持相对时间）

**严格匹配规则**：用预编译正则 `^\d{4}$`（年）、`^\d{4}-\d{2}$`（年-月）、`^\d{4}-\d{2}-\d{2}$`（完整日期）识别格式；对单值/范围两侧的每一段，未命中任一正则就直接抛 `INVALID_DATE_FORMAT`；命中正则后还要走 `datetime.strptime` 校验日期合法性（含闰年、月末、月份范围）。这样可以拒绝 `June 24`、`2024/06`、`24-06`、`2024-13`（无效月份）、`2024-1`（位数不对）、`2024-02-30`（不存在的日期）等输入。

```python
import re
from calendar import monthrange
from datetime import date as date_type, datetime

YEAR_RE = re.compile(r"^\d{4}$")
YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def date_range_to_sql_bounds(arg: str) -> DateRange:
    """
    返回 DateRange(start: "YYYY-MM-DD", end: "YYYY-MM-DD")
    用于 SQL: SUBSTR(value, 1, 10) >= start AND <= end
    """
    arg = arg.strip()
    # ".." 范围
    if ".." in arg:
        left, _, right = arg.partition("..")
        return DateRange(
            _to_start_bound(left.strip()) if left.strip() else "0000-00-00",
            _to_end_bound(right.strip()) if right.strip() else "9999-12-31",
        )
    # 单值
    return DateRange(_to_start_bound(arg), _to_end_bound(arg))

def _validate_month(year: int, month: int) -> None:
    if not (1 <= month <= 12):
        raise InvalidDateFormatError(
            f"Invalid month '{month:02d}' in date input",
            hint="Month must be 01-12",
        )

def _to_start_bound(s: str) -> str:
    if YEAR_RE.match(s):
        return f"{s}-00-00"  # 年 → 含 "只标年" 的条目
    if YEAR_MONTH_RE.match(s):
        _validate_month(int(s[:4]), int(s[5:7]))
        return f"{s}-00"     # 年-月 → 含 "只标年月" 的条目
    if ISO_DATE_RE.match(s):
        # 严格 ISO 日期，再交给 datetime.strptime 校验日期合法性（含闰年/月末）
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError as e:
            raise InvalidDateFormatError(
                f"Invalid date '{s}': {e}",
                hint="Use YYYY-MM-DD",
            )
        return s
    raise InvalidDateFormatError(
        f"Unrecognized date format: '{s}'",
        hint="Supported: YYYY / YYYY-MM / YYYY-MM-DD / X..Y / X.. / ..Y",
    )

def _to_end_bound(s: str) -> str:
    if YEAR_RE.match(s):
        return f"{s}-12-31"
    if YEAR_MONTH_RE.match(s):
        year, month = int(s[:4]), int(s[5:7])
        _validate_month(year, month)
        last_day = monthrange(year, month)[1]
        return f"{s}-{last_day:02d}"
    if ISO_DATE_RE.match(s):
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError as e:
            raise InvalidDateFormatError(f"Invalid date '{s}': {e}", hint="Use YYYY-MM-DD")
        return s
    raise InvalidDateFormatError(
        f"Unrecognized date format: '{s}'",
        hint="Supported: YYYY / YYYY-MM / YYYY-MM-DD / X..Y / X.. / ..Y",
    )
```

**关于日期解析的依赖**：用户输入用严格正则匹配 + stdlib `datetime`/`calendar` 校验，不引入第三方库。Zotero `items.dateAdded` / `items.dateModified` 是 SQLite TIMESTAMP（已是 ISO 格式），用 `datetime.fromisoformat` 即可解析。

转换示例：

| 用户输入 | SQL start | SQL end |
|---|---|---|
| `2024-06-15` | `2024-06-15` | `2024-06-15` |
| `2024-06` | `2024-06-00` | `2024-06-30` |
| `2024` | `2024-00-00` | `2024-12-31` |
| `2024-01..2024-06` | `2024-01-00` | `2024-06-30` |
| `2024-06-15..` | `2024-06-15` | `9999-12-31` |
| `..2024-06-15` | `0000-00-00` | `2024-06-15` |

### 11.5 边界情况

#### `00` 占位与查询的交互

| 存储值 | 查询 `2024`（边界 `2024-00-00`~`2024-12-31`）|
|---|---|
| `2024-00-00` | ✅ 包含（等于下界）|
| `2024-06-00` | ✅ 包含 |
| `2024-06-15` | ✅ 包含 |
| `2023-12-31` | ❌ 排除 |

#### `--include-undated` 选项

默认排除 `date_v.value IS NULL` 的 item，`--include-undated` 包含。

### 11.6 Schema 兼容性检测

启动时检查必需表存在 + feedItems 关键字段（`itemID`、`guid`、`readTime`、`translatedTime`），不匹配抛 `SQLITE_SCHEMA_INCOMPATIBLE`。

### 11.7 性能预估

| 操作 | 预估时间 |
|---|---|
| 打开只读连接 | < 50ms |
| 列出 10 个 feeds + counts | < 100ms |
| 查询 1000 条 feed items（含 date 过滤） | < 300ms |
| 查询 creators（IN 子句） | < 100ms |

---

## 12. 测试策略

### 12.0 网络 mock 工具策略

`respx` 拦截的是 `httpx` 的请求层。本设计涉及两个外部 HTTP 客户端：

- **pyzotero**：内部使用 httpx，理论上 respx 可拦截，但具体能否命中需要在阶段 3 实施时**实测验证**（pyzotero 可能用自己创建的 Client 实例，需要确认 respx 的全局 patch 是否覆盖）
- **webdav4**：底层也是 httpx，但封装层更厚，respx 可能无法直接拦截 WebDAV 请求

**Fallback 策略**（按优先级）：

1. **优先 respx**：如果实测发现 pyzotero/webdav4 的 httpx 调用能被 respx 拦截，按 §12.6 的写法即可
2. **Adapter mock**：如果 respx 覆盖不到，改在 `adapters/zotero_api.py` 和 `adapters/webdav_client.py` 的边界做 mock（用 `pytest-mock` 直接 patch adapter 方法）。代价是测不到 HTTP 细节（headers、URL 拼接、状态码处理），但能覆盖 service 层逻辑
3. **本地测试 server**：如果连 adapter mock 都不够（比如要验证 WebDAV 协议字节级细节），起本地 HTTP/WebDAV server。Python 生态可选 `pytest-httpserver`（HTTP）或 `wsgidav`（WebDAV）。这是阶段 4 §10.6 协议实测的天然产物——验证用的本地 server 可以直接复用为测试 fixture

**实施时机**：阶段 3 第一个用到 pyzotero 的测试就要做 respx 覆盖性实测，结果决定后续测试栈。

---

### 12.1 测试金字塔

- **单元（70%）**：隔离 mock，覆盖边界情况
- **集成（25%）**：真实 sqlite fixture + mock 网络（按 §12.0 选择 mock 策略）
- **E2E（5%）**：真实 API + WebDAV，需环境变量启用

### 12.2 关键测试模块

| 模块 | 类型 | 重点 |
|---|---|---|
| `date_parser` | 单元 + 参数化 | 所有 date 语法 + 边界 + `00` 占位 |
| `webdav_client` | 单元 + 集成 | zip 格式、prop XML、协议正确性 |
| `sqlite_reader` | 单元（用真实 fixture） | LEFT JOIN 正确性、date 过滤、include_undated |
| `attachment_service` | 集成 | 完整上传流程 + 失败回滚 |
| `output` | 单元 | 各格式渲染 + 字段过滤 |
| `envelope` | 单元 | JSON 结构正确性 |

### 12.3 测试 sqlite fixture

`tests/fixtures/build_sqlite.py` 是构造脚本，提交到 git；生成的 `zotero_test.sqlite` 也提交，包含覆盖各种 date 格式的 5 个 feedItems：

| itemID | date_value | 说明 |
|---|---|---|
| 1001 | `2024-06-15 2024-06-15` | 完整日期 |
| 1002 | `2024-06-00 June 2024` | 年-月 |
| 1003 | `2024-00-00 2024` | 仅年 |
| 1004 | `2023-12-31 2023-12-31` | 范围外 |
| 1005 | `NULL` | 无日期 |

### 12.4 覆盖率目标

| 模块 | 目标 |
|---|---|
| `utils/date_parser.py` | 100% |
| `adapters/webdav_client.py` | 95%+ |
| `adapters/sqlite_reader.py` | 90%+ |
| `services/*` | 85%+ |
| `commands/*` | 70%+ |
| `utils/output.py` | 90%+ |
| 总体 | 85%+ |

### 12.5 手动测试清单

| 场景 | 验证方式 |
|---|---|
| **ZFS 后端**：默认配置（无 webdav）下上传 PDF | pyzotero 上传后桌面端能正常拉取并打开 |
| **WebDAV 后端**：CLI 上传的 PDF 能被 Zotero 桌面端识别 | 上传后 Zotero 客户端能正常打开 |
| **后端切换**：同一 library 改 config（加/删 [webdav]）后行为正确 | 删 webdav 后下次上传走 ZFS；加回后走 WebDAV；envelope 的 `data.backend` 与 `meta.backend` 反映正确 |
| **group library 拒绝**：`library_type=group` 配 `[webdav]` 时 `config validate` 报错 | 退出码 1，错误码 `UNSUPPORTED_LIBRARY_TYPE` |
| **`--attach-title` 不污染父 item title**（ZFS + WebDAV 两路径分别测）| `items create --type journalArticle --title "Paper X" --attach paper.pdf --attach-title "Main PDF"` 后：父 item 的 `title=="Paper X"`；attachment item 的 `title=="Main PDF"`。再测一次省略 `--attach-title`：attachment title 应等于文件名（`paper.pdf`），父 item title 仍为 `Paper X`。`items update <key> --attach` 同样验证 |
| **`items attach --title` 是附件 title（无父 item title 歧义）** | `items attach <parent> file.pdf --title "Custom Att"` → attachment.title == "Custom Att"，父 item 不动 |
| **`--reuse-key` ZFS 路径**（spike 通过后再做） | 1) `items attach <parent> file.pdf` 拿到 att-key；2) 改本地 PDF 内容后 `items attach <parent> file.pdf --reuse-key <att-key>`；3) 验证：远端 attachment 的 md5 已更新；父 item 不变；attachment key 保持不变 |
| **`--reuse-key` WebDAV 路径** | 1) `items attach` 上传文件；2) 模拟中断（手动删远端 prop）；3) `items attach <parent> file.pdf --reuse-key <att-key>` 重传；4) 验证：远端 zip+prop 都恢复，桌面端能打开 |
| **`--reuse-key` 不存在的 attachment-key** | `items attach <parent> file.pdf --reuse-key NONEXIST` → 退出码 1，错误码 `ITEM_NOT_FOUND` |
| **ZFS 后端 `--force` 被拒绝** | `items attach <parent> file.pdf --reuse-key <att-key> --force`（profile 无 `[webdav]`）→ 退出码 64，错误码 `MUTUALLY_EXCLUSIVE_ARGS`，stderr 含 §10.0.2.3 的提示文案 |
| **WebDAV 后端 `--force` 跳过 md5 检测** | 1) `items attach` + `--reuse-key` 第一次（远端 md5 已一致）→ 走 unchanged 路径，`data.uploaded=[]`、`data.unchanged=[…]`；2) 同样命令加 `--force` → 走 uploaded 路径，远端 prop 的 mtime 更新 |
| **`--quiet` 不输出 unchanged / failed key**（WebDAV `--reuse-key` md5 命中场景）| `items attach <parent> file.pdf --reuse-key <att-key>` 当远端 md5 与本地一致 → `data.unchanged=[…]`；`--quiet` 输出为空（不含 attachment key）；退出码 0。再加 `--force` 同命令 → `--quiet` 输出 attachment key |
| **mtime 一致性**（仅 WebDAV）| 上传后桌面端不触发"重新上传" |
| **base64 编码方式**（仅 WebDAV）| 用 Zotero 客户端上传 PDF，对比内部文件名 |
| **多平台 sqlite 路径检测** | Linux/macOS/Windows 都跑 `config validate` |
| **大文件上传（100MB PDF）** | 不 OOM、进度条正常 |

### 12.6 CI（可选）

GitHub Actions：
- Python 3.11/3.12 矩阵
- ruff lint + mypy 类型检查
- 单元 + 集成测试 + 覆盖率上传
- E2E 不在 CI 跑（需真实账号）

### 12.7 TDD 节奏

关键模块（`date_parser`、`webdav_client`）严格 TDD；CLI 路由层和 Rich 渲染细节可以先写后测。

---

## 13. 实施顺序建议

按依赖关系分阶段实施：

1. **阶段 1：基础设施**
   - 项目骨架（uv init、pyproject.toml、CI）
   - models/errors.py + models/envelope.py
   - utils/exit_codes.py + utils/output.py 框架
   - utils/audit_log.py（JSONL 写入 + 自动轮转，所有写操作的依赖）
   - utils/date_parser.py（TDD）

2. **阶段 2：配置层**
   - models/config.py（pydantic-settings）
   - commands/config.py（init/show/set/get/validate/profiles）
   - `validate` 实现 §10.0 的 WebDAV + library_type 一致性校验

3. **阶段 3：Zotero API 适配（pyzotero）**
   - **pyzotero spike（首要任务）**：用真实测试账号验证以下假设，全部记录到 `docs/superpowers/specs/spikes/pyzotero-attachment-api.md`：
     1. `attachment_simple` / `attachment_both` / `upload_attachments` / `Zupload` 的实际行为是否与 §10.0.2.1 表格一致（参数、返回值结构、异常类型）
     2. `upload_attachments` + `parentid=None` + `template['key']=existing_key` 是否真的能"重传到已有 attachment"
     3. `unchanged` 返回时是否完全没发生网络上传（用 respx 抓包验证）
     4. respx 是否能拦截 pyzotero 的 httpx 请求（决定 §12.0 mock 策略）
     - 如果实测与 §10.0.2 不符，**回到设计文档修正**，再继续后续步骤
   - adapters/zotero_api.py（pyzotero 包装 + `_select_backend(profile)` 派发 + 异常 → CLI 错误码翻译，按 §10.0.2.6 表）
   - services/item_service.py + commands/items.py（不含 attach；create/update/delete 接入审计日志）
   - services/collection_service.py + commands/collections.py（写操作接入审计日志）
   - services/tag_service.py + commands/tags.py（写操作接入审计日志）
   - services/export_service.py + items export

4. **阶段 4：附件上传（ZFS 默认 + WebDAV 可选）**
   - 阶段 3 spike 已确认 pyzotero 附件 API 行为；本阶段只做封装与协调
   - **手动验证 Zotero WebDAV 协议格式**（仅当本阶段计划支持 WebDAV 后端时；记录到 `docs/superpowers/specs/spikes/webdav-protocol.md`）
   - adapters/zotero_api.py：扩展 ZFS 路径封装（按 §10.0.2.2 命令映射表实现各 CLI 命令对应的 pyzotero 调用）
   - adapters/webdav_client.py（zip + prop + 上传 + storage_path normalize，仅 WebDAV 路径用）
   - services/attachment_service.py：根据 `_select_backend()` 派发；§10.0.1 前置校验 + §10.0.2.5 ZFS 失败回滚 + §10.3 WebDAV 失败回滚 + 审计日志
   - items create/update --attach（场景 A：新建 attachment，两种后端都支持）
   - items attach（含 --reuse-key 场景 B 重传；--force 仅 WebDAV 后端有效，ZFS 后端拒绝并报 `MUTUALLY_EXCLUSIVE_ARGS`）

5. **阶段 5：RSS（SQLite）**
   - adapters/sqlite_reader.py（连接 + schema 检测 + 字段缓存）
   - services/feed_service.py（list + items + date 过滤 + include_undated 参数化）
   - commands/feeds.py

6. **阶段 6：Agent 自省 + 收尾**
   - commands/schema.py（命令树 JSON Schema 自省）
   - 文档与 README

---

## 14. 已确认决策清单

| 决策 | 选择 |
|---|---|
| 核心功能优先级 | C/D 主，A/B/E 基础，RSS 主 |
| WebDAV 配置 | 独立配置（不读 Zotero 客户端配置）；可选段，配了才启用 WebDAV 后端 |
| **附件上传后端** | 默认 ZFS（pyzotero 内建）；profile 配 `[webdav]` 时切换为自实现 WebDAV，由 `_select_backend(profile)` 自动判定 |
| **WebDAV 适用范围** | **仅 personal library**（`library_type = "user"`）；group library 配 `[webdav]` 在 `config validate` 报 `UNSUPPORTED_LIBRARY_TYPE`，attach 操作直接拒绝 |
| RSS 功能 | 仅 list + query items（无 mark-read、无转存） |
| RSS date 过滤精度 | 单日 / 范围 / 开区间 / 年 / 年-月 |
| RSS date 字段含义 | 条目发布日期（itemData 的 `date` 字段） |
| 输出默认格式 | 按命令自动选（agent 友好） |
| `--json` 用途 | 人类写脚本（带完整 envelope） |
| 全局 flag | `--json`、`--profile`、`--quiet`（与 `--json` 互斥） |
| 字段过滤 | `[<profile>.item_fields]` 配置 + `--all-fields` 覆盖 |
| 配置位置 | `~/.config/zotero-cli/config.toml`（XDG） |
| 多 profile | 支持，`--profile NAME` 切换 |
| SQLite 访问 | 直接 `mode=ro&nolock=1`（不复制） |
| SQL 查询 | LEFT JOIN，date 过滤完全在 SQL 完成 |
| 附件命令 | 集成到 `items create/update/attach`（不单独成顶级子命令） |
| 退出码 | 0/1/2/3/4/64/130 语义化 |
| 审计日志 | JSONL，仅写操作，自动轮转 |
| Streaming API / OAuth | 不实现 |

---

## 15. 参考资源

- [Zotero Web API v3 文档](https://www.zotero.org/support/dev/web_api/v3/)
- [pyzotero 文档](https://pyzotero.readthedocs.io/)
- [Zotero schema (userdata.sql)](https://raw.githubusercontent.com/zotero/zotero/main/resource/schema/userdata.sql)
- [Zotero source (multipart date 处理)](https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/timeline.js)
- [webdav4 文档](https://skshetry.github.io/webdav4/)
- [Typer 文档](https://typer.tiangolo.com/)
- [pydantic-settings 文档](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
