"""Load and validate the list of sources to ingest (data/sources.yaml)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

import yaml

SourceType = Literal["html", "pdf"]
_VALID_TYPES = ("html", "pdf")


@dataclass(frozen=True)
class Source:
    """One entry of sources.yaml."""

    url: str
    type: SourceType
    title: str | None = None

    @property
    def doc_id(self) -> str:
        """Stable, readable id from the URL, e.g. ``th-deg-de-living-costs-2024-1a2b3c4d``."""
        return make_doc_id(self.url)


def make_doc_id(url: str) -> str:
    """Build a filesystem-safe document id from a URL (slug + short hash for uniqueness)."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    last = unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1])
    last = re.sub(r"\.(html?|pdf)$", "", last, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "-", f"{host}-{last}".lower()).strip("-")[:60].rstrip("-")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def load_sources(path: Path) -> list[Source]:
    """Read sources.yaml and return validated, de-duplicated sources.

    Raises ValueError with the entry number if an entry is malformed.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a YAML list of sources")

    sources: list[Source] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: entry {i} must be a mapping")
        url = str(entry.get("url", "")).strip()
        kind = str(entry.get("type", "")).strip().lower()
        title = entry.get("title")
        if urlparse(url).scheme not in ("http", "https"):
            raise ValueError(f"{path}: entry {i} has an invalid url: {url!r}")
        if kind not in _VALID_TYPES:
            raise ValueError(f"{path}: entry {i} has type {kind!r}; expected html or pdf")
        if url in seen:
            continue
        seen.add(url)
        sources.append(Source(url=url, type=kind, title=str(title).strip() if title else None))  # type: ignore[arg-type]
    return sources
