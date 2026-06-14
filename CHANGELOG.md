# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `items add-doi --attach` and `--attach-title` to upload a PDF to the DOI-created item in one step, matching `items create`.

## [0.2.3] - 2026-06-13

### Added

- Added configuration documentation for profiles, environment overrides, and command examples.
- Added feed support for dynamic Zotero `itemData` fields, including DOI values.

### Fixed

- Fixed feed field filtering to preserve configured field order.
- Fixed feed item output so abstract notes do not leak into unrelated fields.
- Fixed feed query date handling to avoid field name collisions.

## [0.2.2] - 2026-06-12

### Added

- Added `--version` and `-v` global options to print the CLI version.
- Added `items export --limit` to cap exported item counts.
- Added explicit unsupported export format validation.

### Fixed

- Fixed export format handling to use pyzotero's `content=` export path for all supported export formats.
- Fixed profile config value parsing so numeric-looking strings are preserved instead of being blindly coerced to numbers.

### Changed

- Cleaned up export serialization typing.
- Added `.gitignore` coverage for worktree directories.

## [0.2.1] - 2026-06-11

### Fixed

- Fixed collection-scoped exports to use Zotero's collection items endpoint.
- Fixed `export --output` so exported files are written before JSON envelope output.
- Fixed export handling for BibTeX conversion results returned as `BibDatabase`, `list`, or `dict`.
- Fixed item creation so `add_tags` are merged into Zotero tags instead of being sent as an unsupported API payload field.
- Fixed collection creation result normalization for batched pyzotero responses.

## [0.2.0] - 2026-06-10

### Added

- Added `items add-doi` to create Zotero items from DOI metadata.
- Added Crossref metadata lookup with DOI normalization and validation.
- Added `crossref_email` profile config support for polite Crossref API requests.

### Fixed

- Fixed several CLI output and filtering paths, including dry-run previews, item creation collection payloads, collection item filtering, and string-form Zotero tags.
- Preserved error handling behavior across new DOI and metadata lookup paths.

## [0.1.1] - 2026-06-09

### Fixed

- **ZFS `--reuse-key` now works**: removed the temporary guard that blocked `items attach --reuse-key` on ZFS backend, now that pyzotero 1.13.1 has fixed the upstream `_register_upload` hardcoded `If-None-Match: *` header issue ([pyzotero#322](https://github.com/urschrei/pyzotero/issues/322)).
- **Error codes preserved in ZFS upload path**: `CLIError` subclasses (e.g. `ITEM_NOT_FOUND`, `API_SERVER_ERROR`) from the ZoteroAPI adapter are no longer double-wrapped into generic `CLIError(code="GENERIC")` by `_attach_zfs`.

### Changed

- Bumped `pyzotero` dependency to `>=1.13.1`.
- Updated design doc and DEVELOPMENT.md to reflect `upload_attachments` / `Zupload` compatibility with existing keys (pyzotero >=1.13.1).

## [0.1.0] - 2026-06-08

Initial PyPI release.

[0.2.3]: https://github.com/cywwycedward/zotero-cli/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/cywwycedward/zotero-cli/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/cywwycedward/zotero-cli/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/cywwycedward/zotero-cli/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/cywwycedward/zotero-cli/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/cywwycedward/zotero-cli/releases/tag/v0.1.0
