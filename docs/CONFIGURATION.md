# Configuration

This document describes how to configure `zotero-cli` with `zotero-cli config`
commands or by editing the TOML configuration file directly.

## Configuration File

By default, `zotero-cli` reads:

```text
~/.config/zotero-cli/config.toml
```

If `XDG_CONFIG_HOME` is set, the default path becomes:

```text
$XDG_CONFIG_HOME/zotero-cli/config.toml
```

Commands that write the config file create it with permission `0600`.

For tests or advanced usage, the hidden global option `--config-path` can point
to another file:

```bash
zotero-cli --config-path /path/to/config.toml config show
```

## Profiles

The config file contains one or more profiles. A profile is a complete set of
Zotero API, library, attachment, SQLite, and display-field settings.

The default profile name is `default`. Select another profile with the global
`--profile` option:

```bash
zotero-cli --profile work config show
zotero-cli --profile work items list
```

Create a config file for the selected profile:

```bash
zotero-cli config init
zotero-cli --profile work config init
```

Overwrite an existing config file:

```bash
zotero-cli config init --force
```

List available profiles:

```bash
zotero-cli config profiles
```

## Basic Configuration

A minimal user-library configuration contains `api_key`, `library_id`, and
`library_type`:

```bash
zotero-cli config init
zotero-cli config set api_key "<your-zotero-api-key>"
zotero-cli config set library_id "<your-library-id>"
zotero-cli config set library_type user
zotero-cli config validate
```

The equivalent TOML is:

```toml
[default]
api_key = "<your-zotero-api-key>"
library_id = "<your-library-id>"
library_type = "user"
```

For a group library:

```bash
zotero-cli config set library_type group
zotero-cli config set library_id "<group-library-id>"
```

Group libraries cannot use the `[<profile>.webdav]` section.

## Config Commands

Show the selected profile with secrets masked:

```bash
zotero-cli config show
zotero-cli --profile work config show
```

Set a value. Nested fields use dot paths:

```bash
zotero-cli config set api_key "<key>"
zotero-cli config set webdav.password "<password>"
zotero-cli config set sqlite.path "/home/user/Zotero/zotero.sqlite"
```

Get a value. Sensitive values such as `api_key` and `password` are masked:

```bash
zotero-cli config get library_id
zotero-cli config get webdav.password
```

Validate the selected profile:

```bash
zotero-cli config validate
```

When using `config set`, all values are command-line strings. `true` and
`false` are stored as booleans. List fields are comma-separated strings. Numeric
fields such as `webdav.timeout` are validated as numbers, even if the TOML write
stores the command-line value as a string.

## Direct TOML Editing

You can edit the config file directly. The top-level TOML tables are profile
names:

```toml
[default]
api_key = "..."
library_id = "12345678"
library_type = "user"
crossref_email = "you@example.com"

[default.webdav]
url = "https://dav.example.com"
storage_path = "/zotero"
username = "myuser"
password = "mypass"
timeout = 120
verify_ssl = true

[default.sqlite]
path = "/home/user/Zotero/zotero.sqlite"

[default.item_fields]
list = ["key", "title", "creators", "date", "itemType", "tags"]

[default.feed_item_fields]
list = ["feed_id", "item_id", "title", "date", "url", "read_time"]

[default.feed_fields]
list = ["feed_id", "name", "url", "unread_count", "total_count"]

[work]
api_key = "..."
library_id = "987654"
library_type = "group"
```

After editing the file, run:

```bash
zotero-cli config validate
```

## Configurable Fields

| Field | Type | Required | Default | How to set with CLI |
|---|---:|---:|---|---|
| `api_key` | string | yes | none | `zotero-cli config set api_key "<key>"` |
| `library_id` | string | yes | none | `zotero-cli config set library_id "<id>"` |
| `library_type` | `"user"` or `"group"` | yes | none | `zotero-cli config set library_type user` |
| `crossref_email` | string or omitted | no | omitted | `zotero-cli config set crossref_email "you@example.com"` |
| `webdav.url` | string | required if `webdav` is used | none | `zotero-cli config set webdav.url "https://dav.example.com"` |
| `webdav.storage_path` | string | no | `"/zotero"` | `zotero-cli config set webdav.storage_path "/zotero"` |
| `webdav.username` | string | required if `webdav` is used | none | `zotero-cli config set webdav.username "<user>"` |
| `webdav.password` | string | required if `webdav` is used | none | `zotero-cli config set webdav.password "<password>"` |
| `webdav.timeout` | integer | no | `120` | `zotero-cli config set webdav.timeout 120` |
| `webdav.verify_ssl` | boolean | no | `true` | `zotero-cli config set webdav.verify_ssl false` |
| `sqlite.path` | string or omitted | no | auto-detected when possible | `zotero-cli config set sqlite.path "/home/user/Zotero/zotero.sqlite"` |
| `item_fields.list` | list of strings | no | `["key", "title", "creators", "date", "itemType", "tags"]` | `zotero-cli config set item_fields.list "key,title,date"` |
| `feed_item_fields.list` | list of strings | no | `["feed_id", "item_id", "title", "date", "url", "read_time"]` | `zotero-cli config set feed_item_fields.list "feed_id,title,date"` |
| `feed_fields.list` | list of strings | no | `["feed_id", "name", "url", "unread_count", "total_count"]` | `zotero-cli config set feed_fields.list "feed_id,name,url"` |

### `api_key`

Zotero API key for the selected library.

TOML:

```toml
[default]
api_key = "..."
```

CLI:

```bash
zotero-cli config set api_key "<your-zotero-api-key>"
```

`config show` and `config get api_key` mask this value in output.

### `library_id`

Zotero user ID or group library ID. It is stored as a string, so numeric-looking
IDs should still be quoted when editing TOML directly.

TOML:

```toml
[default]
library_id = "12345678"
```

CLI:

```bash
zotero-cli config set library_id "12345678"
```

### `library_type`

Library type. Valid values are:

| Value | Meaning |
|---|---|
| `user` | Personal Zotero library |
| `group` | Zotero group library |

TOML:

```toml
[default]
library_type = "user"
```

CLI:

```bash
zotero-cli config set library_type user
```

`library_type = "group"` is incompatible with WebDAV attachment storage.

### `crossref_email`

Optional email address sent to CrossRef when DOI metadata is queried. Empty
strings are treated as omitted. If set, the value must contain `@`.

TOML:

```toml
[default]
crossref_email = "you@example.com"
```

CLI:

```bash
zotero-cli config set crossref_email "you@example.com"
```

### `webdav`

The optional `[<profile>.webdav]` section enables WebDAV attachment upload for
user libraries. If the section is omitted, attachment upload uses Zotero File
Storage.

Minimal WebDAV TOML:

```toml
[default.webdav]
url = "https://dav.example.com"
username = "myuser"
password = "mypass"
```

CLI:

```bash
zotero-cli config set webdav.url "https://dav.example.com"
zotero-cli config set webdav.username "myuser"
zotero-cli config set webdav.password "mypass"
```

`webdav.password` is masked by `config show` and `config get`.

#### `webdav.url`

Base WebDAV server URL.

```bash
zotero-cli config set webdav.url "https://dav.example.com"
```

#### `webdav.storage_path`

Remote directory used for Zotero attachment storage.

Rules:

- Default is `/zotero`.
- Use an empty string to store files at the server root.
- Non-empty values must start with `/`.
- `/` is rejected; use an empty string for the server root.
- Values containing `..` path segments or `//` are rejected.
- A trailing slash is normalized away, so `/zotero/` becomes `/zotero`.

TOML:

```toml
[default.webdav]
storage_path = "/zotero"
```

CLI:

```bash
zotero-cli config set webdav.storage_path "/zotero"
```

To use the WebDAV server root:

```bash
zotero-cli config set webdav.storage_path ""
```

#### `webdav.username`

WebDAV username.

```bash
zotero-cli config set webdav.username "myuser"
```

#### `webdav.password`

WebDAV password or app password.

```bash
zotero-cli config set webdav.password "mypass"
```

#### `webdav.timeout`

WebDAV network timeout in seconds. Default is `120`.

TOML:

```toml
[default.webdav]
timeout = 120
```

CLI:

```bash
zotero-cli config set webdav.timeout 120
```

#### `webdav.verify_ssl`

Whether HTTPS certificates are verified for WebDAV requests. Default is `true`.

TOML:

```toml
[default.webdav]
verify_ssl = true
```

CLI:

```bash
zotero-cli config set webdav.verify_ssl false
```

## SQLite Configuration

The optional `[<profile>.sqlite]` section configures the local Zotero SQLite
database path used by feed commands.

```toml
[default.sqlite]
path = "/home/user/Zotero/zotero.sqlite"
```

CLI:

```bash
zotero-cli config set sqlite.path "/home/user/Zotero/zotero.sqlite"
```

If `sqlite.path` is omitted, `zotero-cli` tries to auto-detect
`zotero.sqlite` in this order:

1. `$ZOTERO_DATA_DIR/zotero.sqlite`
2. `~/Zotero/zotero.sqlite`
3. `~/snap/zotero-snap/common/Zotero/zotero.sqlite`
4. `~/.var/app/org.zotero.Zotero/data/Zotero/zotero.sqlite`

## Display Fields

Display field lists control which fields are shown in list-style output. Values
are field names as strings.

When using `config set`, pass a comma-separated string:

```bash
zotero-cli config set item_fields.list "key,title,date"
```

When editing TOML directly, use a TOML array:

```toml
[default.item_fields]
list = ["key", "title", "date"]
```

### `item_fields.list`

Fields shown for item list and search output.

Default:

```toml
[default.item_fields]
list = ["key", "title", "creators", "date", "itemType", "tags"]
```

CLI:

```bash
zotero-cli config set item_fields.list "key,title,creators,date,itemType,tags"
```

### `feed_item_fields.list`

Fields shown for feed item output.

Default:

```toml
[default.feed_item_fields]
list = ["feed_id", "item_id", "title", "date", "url", "read_time"]
```

CLI:

```bash
zotero-cli config set feed_item_fields.list "feed_id,item_id,title,date,url,read_time"
```

### `feed_fields.list`

Fields shown for feed list output.

Default:

```toml
[default.feed_fields]
list = ["feed_id", "name", "url", "unread_count", "total_count"]
```

CLI:

```bash
zotero-cli config set feed_fields.list "feed_id,name,url,unread_count,total_count"
```

## Environment Overrides

Environment variables can override selected fields at load time. They do not
rewrite the TOML file.

The format is:

```text
ZOTERO_CLI_<PROFILE>_<KEY>
```

`<PROFILE>` is the upper-case profile name. For the `default` profile, use
`ZOTERO_CLI_DEFAULT_...`.

Supported environment overrides:

| Environment variable | Overrides |
|---|---|
| `ZOTERO_CLI_<PROFILE>_API_KEY` | `api_key` |
| `ZOTERO_CLI_<PROFILE>_LIBRARY_ID` | `library_id` |
| `ZOTERO_CLI_<PROFILE>_LIBRARY_TYPE` | `library_type` |
| `ZOTERO_CLI_<PROFILE>_WEBDAV_URL` | `webdav.url` |
| `ZOTERO_CLI_<PROFILE>_WEBDAV_STORAGE_PATH` | `webdav.storage_path` |
| `ZOTERO_CLI_<PROFILE>_WEBDAV_USERNAME` | `webdav.username` |
| `ZOTERO_CLI_<PROFILE>_WEBDAV_PASSWORD` | `webdav.password` |
| `ZOTERO_CLI_<PROFILE>_WEBDAV_TIMEOUT` | `webdav.timeout` |
| `ZOTERO_CLI_<PROFILE>_WEBDAV_VERIFY_SSL` | `webdav.verify_ssl` |
| `ZOTERO_CLI_<PROFILE>_SQLITE_PATH` | `sqlite.path` |
| `ZOTERO_CLI_<PROFILE>_ITEM_FIELDS_LIST` | `item_fields.list` |
| `ZOTERO_CLI_<PROFILE>_FEED_ITEM_FIELDS_LIST` | `feed_item_fields.list` |

Examples:

```bash
export ZOTERO_CLI_DEFAULT_API_KEY="<key>"
export ZOTERO_CLI_DEFAULT_WEBDAV_PASSWORD="<password>"
export ZOTERO_CLI_DEFAULT_WEBDAV_VERIFY_SSL=false
export ZOTERO_CLI_DEFAULT_ITEM_FIELDS_LIST="key,title,date"
zotero-cli config show
```

Boolean environment values for `webdav.verify_ssl` are true when the value is
`true`, `1`, or `yes` after lower-casing. Other values are false.

## Validation Rules

`zotero-cli config validate` checks the selected profile.

Important rules:

- Unknown fields are rejected.
- `library_type` must be `user` or `group`.
- `library_type = "group"` cannot be used with `[<profile>.webdav]`.
- If `[<profile>.webdav]` exists, `url`, `username`, and `password` are required.
- `webdav.storage_path` must follow the path rules described above.
- `webdav.timeout` must be an integer.
- `crossref_email` must be empty, omitted, or contain `@`.

