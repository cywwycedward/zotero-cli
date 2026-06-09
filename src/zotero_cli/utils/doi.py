"""src/zotero_cli/utils/doi.py — DOI normalization and validation."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")
_TRAILING_PUNCT = ".,:;)]"


def normalize_doi(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None

    lower = value.lower()
    if lower.startswith("doi:"):
        value = value[4:]
    elif lower.startswith("http://") or lower.startswith("https://"):
        parsed = urlparse(value)
        if parsed.hostname in ("doi.org", "dx.doi.org"):
            value = unquote(parsed.path.lstrip("/"))

    while value and value[-1] in _TRAILING_PUNCT:
        value = value[:-1]

    return value if value else None


def validate_doi(value: str) -> bool:
    return bool(_DOI_PATTERN.match(value))
