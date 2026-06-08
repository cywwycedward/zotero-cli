# zotero-cli

[![CI](https://github.com/cywwycedward/zotero-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/cywwycedward/zotero-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Single-user, agent-first CLI for Zotero — literature management, PDF upload, RSS query.

## Installation

```bash
# From PyPI after the first release is published
uv tool install zotero

# From source
git clone https://github.com/cywwycedward/zotero-cli.git
cd zotero-cli
uv sync --extra dev
uv run zotero-cli --help
```

## Quick Start

```bash
# Initialize config
zotero-cli config init

# Set API key
zotero-cli config set api_key <your-zotero-api-key>
zotero-cli config set library_id <your-library-id>

# List items
zotero-cli items list

# Attach a PDF (ZFS default)
zotero-cli items create --type journalArticle --title "My Paper" --attach paper.pdf
```

## Commands

| Group | Commands |
|---|---|
| `items` | list, search, show, create, update, delete, attach, export |
| `collections` | list, show, create, delete, add-items, remove-items |
| `tags` | list, add, remove, rename, delete |
| `feeds` | list, show, items |
| `config` | init, show, set, get, validate, profiles |
| `schema` | JSON command tree introspection |

## Global Flags

```
--json        JSON envelope output
--profile     Profile name (default: "default")
--quiet, -q   Quiet mode: keys only
```

## Output Modes

- **Default**: Human-readable (KV, tree, summary, YAML) — designed for agent consumption
- **`--json`**: Full JSON envelope with `ok`, `data`, `error`, `meta` — for scripts and `jq`
- **`--quiet`**: Keys only, one per line — for `xargs` pipelining

## Configuration

`~/.config/zotero-cli/config.toml` (permission `0600`):

```toml
[default]
api_key = "..."
library_id = "12345678"
library_type = "user"

[default.webdav]          # Optional: enables WebDAV attachment upload
url = "https://dav.example.com"
storage_path = "/zotero"
username = "myuser"
password = "mypass"

[default.sqlite]
path = "/home/user/Zotero/zotero.sqlite"
```

Environment overrides: `ZOTERO_CLI_<PROFILE>_<KEY>` (e.g. `ZOTERO_CLI_DEFAULT_API_KEY`).

## Development

```bash
uv sync --extra dev
uv run ruff check src tests
uv run mypy src
uv run pytest --cov=src
uv build
```

See `DEVELOPMENT.md` for the full development guide and `CONTRIBUTING.md` for contribution expectations.
