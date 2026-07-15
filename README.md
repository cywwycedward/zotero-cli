# zotero-cli

[![CI](https://github.com/cywwycedward/zotero-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/cywwycedward/zotero-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)

English | [简体中文](README-zh.md)

Single-user, agent-first CLI for Zotero: manage literature, create items from
DOIs, upload PDFs, query Zotero RSS feeds, and produce script-friendly output.

`zotero-cli` is built for researchers and automation agents that need a
predictable command line interface around Zotero. It wraps the Zotero Web API for
library operations, can read Zotero's local SQLite database for RSS feed queries,
and supports both Zotero File Storage and WebDAV-style attachment upload.

## Features

- Manage Zotero items, collections, and tags from the terminal.
- Create items from CrossRef metadata with `items add-doi`.
- Find existing library items by exact DOI with `items find-doi`.
- Attach PDFs through Zotero File Storage by default, or WebDAV when configured.
- Query Zotero RSS feeds from the local `zotero.sqlite` database.
- Export items as BibTeX, RIS, CSL JSON, and other Zotero-supported formats.
- Use human-readable output, JSON envelopes, or key-only quiet mode.
- Keep separate user or group libraries in named profiles.
- Inspect the command tree with `zotero-cli schema` for automation.

## Installation

Install the published CLI with `uv`:

```bash
uv tool install zotero
zotero-cli --version
```

Install the latest code directly from GitHub:

```bash
uv tool install git+https://github.com/cywwycedward/zotero-cli.git
zotero-cli --version
```

Install from source for development:

```bash
git clone https://github.com/cywwycedward/zotero-cli.git
cd zotero-cli
uv sync --extra dev
uv run zotero-cli --help
```

The project package name is `zotero`; the console command is `zotero-cli`.

## Quick Start

Create a profile and add your Zotero API credentials:

```bash
zotero-cli config init
zotero-cli config set api_key "<your-zotero-api-key>"
zotero-cli config set library_id "<your-library-id>"
zotero-cli config set library_type user
zotero-cli config validate
```

List and search items:

```bash
zotero-cli items list --limit 20
zotero-cli items search "machine learning" --limit 10
zotero-cli items show ABCD1234
```

Create items manually or from a DOI:

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

Attach a PDF and export references:

```bash
zotero-cli items attach ABCD1234 ./paper.pdf --title "Accepted manuscript"
zotero-cli items export --format bibtex --collection COLL1234 --output references.bib
```

## Configuration

`zotero-cli` reads profiles from:

```text
~/.config/zotero-cli/config.toml
```

If `XDG_CONFIG_HOME` is set, the path becomes:

```text
$XDG_CONFIG_HOME/zotero-cli/config.toml
```

A minimal user-library profile:

```toml
[default]
api_key = "..."
library_id = "12345678"
library_type = "user"
```

Use a group library by setting `library_type = "group"` and the group library
ID. Group libraries cannot use WebDAV attachment storage.

### Profiles

The default profile is `default`. Select another profile with `--profile`:

```bash
zotero-cli --profile work config init
zotero-cli --profile work items list
zotero-cli config profiles
```

### Environment Overrides

Profile values can be overridden with environment variables:

```bash
export ZOTERO_CLI_DEFAULT_API_KEY="..."
export ZOTERO_CLI_DEFAULT_LIBRARY_ID="12345678"
export ZOTERO_CLI_DEFAULT_LIBRARY_TYPE="user"
```

The prefix is `ZOTERO_CLI_<PROFILE>_`, where `<PROFILE>` is uppercased.

### WebDAV Attachments

Without WebDAV settings, attachments use Zotero File Storage through pyzotero.
Add a profile-specific WebDAV section to switch attachment uploads to the
self-managed WebDAV backend:

```toml
[default.webdav]
url = "https://dav.example.com"
storage_path = "/zotero"
username = "myuser"
password = "mypass"
timeout = 120
verify_ssl = true
```

### RSS Feed Queries

Feed commands read Zotero's local SQLite database. Configure the path when
auto-detection is not enough:

```toml
[default.sqlite]
path = "/home/user/Zotero/zotero.sqlite"
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for all fields, profile
rules, environment variables, and examples.

## Command Overview

| Group | Purpose | Commands |
|---|---|---|
| `items` | Read, write, attach, export, and DOI workflows | `list`, `search`, `show`, `find-doi`, `create`, `add-doi`, `update`, `delete`, `attach`, `export` |
| `collections` | Collection tree and membership management | `list`, `show`, `create`, `delete`, `add-items`, `remove-items` |
| `tags` | Tag listing and batch tag operations | `list`, `add`, `remove`, `rename`, `delete` |
| `feeds` | Local Zotero RSS feed inspection | `list`, `show`, `items` |
| `config` | Profile and credential management | `init`, `show`, `set`, `get`, `validate`, `profiles` |
| `schema` | JSON command tree introspection | `schema`, `schema --command items.list` |

Global options:

```text
--json              Output as a JSON envelope
--profile TEXT      Profile name (default: default)
--quiet, -q         Quiet mode: keys only
--version, -v       Show version and exit
```

## Output Modes

Default output is compact and human-readable, with key-value blocks, lists,
trees, summaries, YAML, or raw export bytes depending on the command.

Use `--json` for scripts:

```bash
zotero-cli --json items list --limit 1
```

JSON output uses a stable envelope:

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

Use `--quiet` when a command has a key-oriented output that you want to pipe:

```bash
zotero-cli --quiet items find-doi "10.1145/3368089.3409742" | xargs -r -n1 zotero-cli items show
```

`--json` and `--quiet` are mutually exclusive.

## Examples

### DOI Workflow

Check whether a DOI already exists, then create it from CrossRef metadata if
needed:

```bash
zotero-cli items find-doi "doi:10.1145/3368089.3409742"
zotero-cli items add-doi "10.1145/3368089.3409742" --collection COLL1234 --tags "systems"
```

Set `crossref_email` for CrossRef polite-pool requests:

```bash
zotero-cli config set crossref_email "you@example.com"
```

### PDF Attachment

Create a Zotero item and attach a PDF in one command:

```bash
zotero-cli items create \
  --type journalArticle \
  --title "A Useful Paper" \
  --attach ./paper.pdf \
  --attach-title "Publisher PDF"
```

Attach to an existing item:

```bash
zotero-cli items attach ABCD1234 ./paper.pdf --dry-run
zotero-cli items attach ABCD1234 ./paper.pdf
```

### RSS Feed Query

List feed subscriptions and query a feed by date:

```bash
zotero-cli feeds list
zotero-cli feeds items 42 --date 2026-06 --limit 20
zotero-cli feeds items 42 --date 2026-01-01..2026-06-30 --include-undated
```

### Export

Write a collection-scoped bibliography:

```bash
zotero-cli items export --format bibtex --collection COLL1234 --output references.bib
```

Print CSL JSON to stdout:

```bash
zotero-cli items export --format csljson --limit 10
```

## Development

Set up the project:

```bash
uv sync --extra dev
```

Run the local checks:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest --cov=src
uv build
```

Useful project docs:

- [DEVELOPMENT.md](DEVELOPMENT.md) - development workflow and architecture rules
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution expectations
- [CHANGELOG.md](CHANGELOG.md) - release history
- [SECURITY.md](SECURITY.md) - security policy
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - full configuration reference

## License

This project is licensed under the [MIT License](LICENSE).
