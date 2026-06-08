# Security Policy

zotero-cli handles local configuration that can contain Zotero API keys and WebDAV credentials.
Please do not include real credentials, personal Zotero databases, or private PDFs in issues,
pull requests, logs, or test fixtures.

## Supported Versions

Until the first stable release, security fixes target the `main` branch and the latest published
release, if one exists.

## Reporting a Vulnerability

Use GitHub Security Advisories for this repository when available. If advisories are not enabled,
open a public issue that asks for a secure contact path, but do not include vulnerability details
or secrets in the issue body.

Please include:

- The affected command or component.
- Whether credentials, local files, or remote Zotero/WebDAV data may be exposed.
- Reproduction steps using synthetic data.

Maintainers will triage reports on a best-effort basis and coordinate a fix before public disclosure.
