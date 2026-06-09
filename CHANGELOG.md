# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-06-09

### Fixed

- **ZFS `--reuse-key` now works**: removed the temporary guard that blocked `items attach --reuse-key` on ZFS backend, now that pyzotero 1.13.1 has fixed the upstream `_register_upload` hardcoded `If-None-Match: *` header issue ([pyzotero#322](https://github.com/urschrei/pyzotero/issues/322)).
- **Error codes preserved in ZFS upload path**: `CLIError` subclasses (e.g. `ITEM_NOT_FOUND`, `API_SERVER_ERROR`) from the ZoteroAPI adapter are no longer double-wrapped into generic `CLIError(code="GENERIC")` by `_attach_zfs`.

### Changed

- Bumped `pyzotero` dependency to `>=1.13.1`.
- Updated design doc and DEVELOPMENT.md to reflect `upload_attachments` / `Zupload` compatibility with existing keys (pyzotero >=1.13.1).

## [0.1.0] - 2026-06-08

Initial PyPI release.

[0.1.1]: https://github.com/cywwycedward/zotero-cli/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cywwycedward/zotero-cli/releases/tag/v0.1.0
