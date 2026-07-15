# zotero-cli

[![CI](https://github.com/cywwycedward/zotero-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/cywwycedward/zotero-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)

[English](README.md) | 简体中文

面向单用户、agent-first 的 Zotero 命令行工具：管理文献、通过 DOI 创建条目、上传
PDF、查询 Zotero RSS feed，并输出适合脚本处理的结果。

`zotero-cli` 面向需要稳定命令行接口的研究者和自动化 agent。它使用 Zotero Web
API 执行文献库操作，可以只读 Zotero 本地 SQLite 数据库来查询 RSS feed，并支持
Zotero File Storage 与 WebDAV 风格的附件上传。

## 功能特性

- 在终端中管理 Zotero 条目、集合和标签。
- 使用 `items add-doi` 从 CrossRef 元数据创建条目。
- 使用 `items find-doi` 按精确 DOI 查找已有条目。
- 默认通过 Zotero File Storage 上传 PDF；配置 WebDAV 后可切换到 WebDAV 后端。
- 从本地 `zotero.sqlite` 查询 Zotero RSS feed。
- 导出 BibTeX、RIS、CSL JSON 以及其他 Zotero 支持的格式。
- 支持人类可读输出、JSON envelope 输出和仅输出 key 的 quiet 模式。
- 用命名 profile 区分个人库或群组库。
- 使用 `zotero-cli schema` 输出命令树，便于自动化集成。

## 安装

使用 `uv` 安装已发布的 CLI：

```bash
uv tool install zotero
zotero-cli --version
```

直接从 GitHub 安装最新代码：

```bash
uv tool install git+https://github.com/cywwycedward/zotero-cli.git
zotero-cli --version
```

从源码安装用于开发：

```bash
git clone https://github.com/cywwycedward/zotero-cli.git
cd zotero-cli
uv sync --extra dev
uv run zotero-cli --help
```

项目包名是 `zotero`；命令行入口是 `zotero-cli`。

## 快速开始

创建 profile 并写入 Zotero API 凭据：

```bash
zotero-cli config init
zotero-cli config set api_key "<your-zotero-api-key>"
zotero-cli config set library_id "<your-library-id>"
zotero-cli config set library_type user
zotero-cli config validate
```

列出和搜索条目：

```bash
zotero-cli items list --limit 20
zotero-cli items search "machine learning" --limit 10
zotero-cli items show ABCD1234
```

手动创建条目，或通过 DOI 创建条目：

```bash
zotero-cli items create \
  --type journalArticle \
  --title "My Paper" \
  --doi "10.1145/3368089.3409742" \
  --tags "reading,systems"

zotero-cli items add-doi "https://doi.org/10.1145/3368089.3409742" \
  --tags "to-read" \
  --dry-run
```

上传 PDF 并导出引用：

```bash
zotero-cli items attach ABCD1234 ./paper.pdf --title "Accepted manuscript"
zotero-cli items export --format bibtex --collection COLL1234 --output references.bib
```

## 配置

`zotero-cli` 从以下位置读取 profile：

```text
~/.config/zotero-cli/config.toml
```

如果设置了 `XDG_CONFIG_HOME`，路径会变为：

```text
$XDG_CONFIG_HOME/zotero-cli/config.toml
```

最小的个人库 profile：

```toml
[default]
api_key = "..."
library_id = "12345678"
library_type = "user"
```

使用群组库时，将 `library_type` 设为 `"group"`，并填写群组库 ID。群组库不能使用
WebDAV 附件存储。

### Profile

默认 profile 是 `default`。用 `--profile` 选择其他 profile：

```bash
zotero-cli --profile work config init
zotero-cli --profile work items list
zotero-cli config profiles
```

### 环境变量覆盖

可以用环境变量覆盖 profile 中的值：

```bash
export ZOTERO_CLI_DEFAULT_API_KEY="..."
export ZOTERO_CLI_DEFAULT_LIBRARY_ID="12345678"
export ZOTERO_CLI_DEFAULT_LIBRARY_TYPE="user"
```

前缀格式是 `ZOTERO_CLI_<PROFILE>_`，其中 `<PROFILE>` 使用大写。

### WebDAV 附件

未配置 WebDAV 时，附件通过 pyzotero 使用 Zotero File Storage 上传。为某个
profile 添加 WebDAV 配置后，附件上传会切换到自管理 WebDAV 后端：

```toml
[default.webdav]
url = "https://dav.example.com"
storage_path = "/zotero"
username = "myuser"
password = "mypass"
timeout = 120
verify_ssl = true
```

### RSS Feed 查询

Feed 命令读取 Zotero 本地 SQLite 数据库。自动检测不够时，可以显式配置路径：

```toml
[default.sqlite]
path = "/home/user/Zotero/zotero.sqlite"
```

完整字段、profile 规则、环境变量和示例见
[docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 命令概览

| 命令组 | 用途 | 命令 |
|---|---|---|
| `items` | 读取、写入、附件、导出和 DOI 工作流 | `list`, `search`, `show`, `find-doi`, `create`, `add-doi`, `update`, `delete`, `attach`, `export` |
| `collections` | 集合树和集合成员管理 | `list`, `show`, `create`, `delete`, `add-items`, `remove-items` |
| `tags` | 标签列表和批量标签操作 | `list`, `add`, `remove`, `rename`, `delete` |
| `feeds` | 本地 Zotero RSS feed 查询 | `list`, `show`, `items` |
| `config` | Profile 和凭据管理 | `init`, `show`, `set`, `get`, `validate`, `profiles` |
| `schema` | JSON 命令树自省 | `schema`, `schema --command items.list` |

全局选项：

```text
--json              输出 JSON envelope
--profile TEXT      Profile 名称（默认：default）
--quiet, -q         Quiet 模式：仅输出 key
--version, -v       显示版本并退出
```

## 输出模式

默认输出紧凑且适合人阅读；根据命令不同，会使用 key-value 块、列表、树、摘要、
YAML 或原始导出字节。

使用 `--json` 便于脚本处理：

```bash
zotero-cli --json items list --limit 1
```

JSON 输出使用稳定 envelope：

```json
{
  "ok": true,
  "data": [],
  "error": null,
  "meta": {
    "command": "items.list",
    "elapsed_ms": 12
  }
}
```

当某个命令有以 key 为核心的输出，并且你想管道传递时，使用 `--quiet`：

```bash
zotero-cli --quiet items find-doi "10.1145/3368089.3409742" | xargs -r -n1 zotero-cli items show
```

`--json` 和 `--quiet` 互斥。

## 示例

### DOI 工作流

先检查某个 DOI 是否已存在；如果不存在，再从 CrossRef 元数据创建：

```bash
zotero-cli items find-doi "doi:10.1145/3368089.3409742"
zotero-cli items add-doi "10.1145/3368089.3409742" --collection COLL1234 --tags "systems"
```

设置 `crossref_email`，用于 CrossRef polite-pool 请求：

```bash
zotero-cli config set crossref_email "you@example.com"
```

### PDF 附件

创建 Zotero 条目并在同一条命令中上传 PDF：

```bash
zotero-cli items create \
  --type journalArticle \
  --title "A Useful Paper" \
  --attach ./paper.pdf \
  --attach-title "Publisher PDF"
```

给已有条目添加附件：

```bash
zotero-cli items attach ABCD1234 ./paper.pdf --dry-run
zotero-cli items attach ABCD1234 ./paper.pdf
```

### RSS Feed 查询

列出 feed 订阅，并按日期查询某个 feed：

```bash
zotero-cli feeds list
zotero-cli feeds items 42 --date 2026-06 --limit 20
zotero-cli feeds items 42 --date 2026-01-01..2026-06-30 --include-undated
```

### 导出

导出某个集合的参考文献：

```bash
zotero-cli items export --format bibtex --collection COLL1234 --output references.bib
```

输出 CSL JSON 到标准输出：

```bash
zotero-cli items export --format csljson --limit 10
```

## 开发

初始化开发环境：

```bash
uv sync --extra dev
```

运行本地检查：

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest --cov=src
uv build
```

常用项目文档：

- [DEVELOPMENT.md](DEVELOPMENT.md) - 开发流程和架构规则
- [CONTRIBUTING.md](CONTRIBUTING.md) - 贡献规范
- [CHANGELOG.md](CHANGELOG.md) - 发布历史
- [SECURITY.md](SECURITY.md) - 安全策略
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - 完整配置参考

## 许可证

本项目使用 [MIT License](LICENSE) 授权。
