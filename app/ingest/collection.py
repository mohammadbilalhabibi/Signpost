"""Ingest a curated local source collection (sources.json + text/ and documents/).

The collection's ``sources.json`` is the source of truth: only entries with
``ingest: true`` are used, each exactly once, from its clean text copy
(``text_path``) or, if that is missing, its PDF (``pdf_path``). Source metadata
(ID, original URL, publisher, dates, edition/semester, notes, ...) is copied into
every document and chunk so answers can cite the original page and keep figures
scoped to their period. Documentation, review notes, evaluation questions and
``reference_only/`` are never part of the corpus.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from app.ingest.chunker import Chunker
from app.ingest.extract import extract_pdf
from app.ingest.jsonl import write_jsonl
from app.ingest.language import detect_language
from app.ingest.pipeline import IngestReport

logger = logging.getLogger(__name__)

SOURCES_FILE = "sources.json"
# Never part of the answer corpus (configuration, documentation, tests, reference copies).
EXCLUDED_DIRS = frozenset({"reference_only"})
EXCLUDED_FILES = frozenset(
    {
        "README.md",
        "Source_Guide.pdf",
        "source_review.json",
        "evaluation_questions.json",
        "sources.json",
        "sources.csv",
    }
)
# Metadata carried into every chunk (keys of sources.json entries).
META_FIELDS = (
    "publisher",
    "source_language",
    "source_format",
    "topic",
    "geographic_scope",
    "accessed_at",
    "source_document_date",
    "edition_or_period",
    "note",
)


class CollectionError(ValueError):
    """The collection is malformed or a source cannot be used."""


@dataclass(frozen=True)
class CollectionSource:
    """One entry of sources.json."""

    id: str
    title: str
    source_url: str
    ingest: bool
    language: str
    text_path: str | None
    pdf_path: str | None
    sha256: str | None
    meta: dict[str, Any]


def load_collection(collection_dir: Path) -> list[CollectionSource]:
    """Read and validate ``sources.json``; returns every entry (also ``ingest: false``)."""
    path = Path(collection_dir) / SOURCES_FILE
    if not path.exists():
        raise CollectionError(f"{path} not found; set COLLECTION_DIR to the collection folder")
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("sources") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise CollectionError(f"{path}: expected a 'sources' list")

    sources: list[CollectionSource] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        missing = [k for k in ("id", "title", "source_url", "ingest") if k not in entry]
        if missing:
            raise CollectionError(f"{path}: entry {i} lacks {', '.join(missing)}")
        if entry["id"] in seen:
            raise CollectionError(f"{path}: duplicate source id {entry['id']}")
        seen.add(entry["id"])
        sources.append(
            CollectionSource(
                id=str(entry["id"]),
                title=str(entry["title"]).strip(),
                source_url=str(entry["source_url"]).strip(),
                ingest=entry["ingest"] is True,
                language=str(entry.get("language") or "unknown"),
                text_path=entry.get("text_path") or None,
                pdf_path=entry.get("pdf_path") or None,
                sha256=entry.get("sha256") or None,
                meta={k: entry.get(k) for k in META_FIELDS},
            )
        )
    return sources


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown file into its YAML front matter (``---`` block) and body."""
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4 :].lstrip("\n")
    return (meta if isinstance(meta, dict) else {}), body


_LINK_LINE_RE = re.compile(r"^\s*\[([^\]]+)\]\(([^)\s]+)\)\s*$")
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def extract_links(body: str) -> tuple[str, list[dict[str, str]]]:
    """Move Markdown links out of the text into a list of ``{text, url, anchor}``.

    The text copies repeat every link on its own line after the item it belongs to
    (``- Application of Enrollment`` then ``[Application of Enrollment](https://...)``).
    Those URL lines add noise to keyword and vector search (URLs contain German words)
    and inflate chunks, so they are removed from the indexed text; ``anchor`` is the
    preceding text line, used to attach the link to the right chunk. ``mailto:`` links
    are dropped because the address is already in the text. Inline links keep their
    text.
    """
    lines: list[str] = []
    links: list[dict[str, str]] = []
    anchor = ""
    for line in body.split("\n"):
        match = _LINK_LINE_RE.match(line)
        if match:
            text, url = match.group(1).strip(), match.group(2)
            if not url.startswith("mailto:"):
                links.append({"text": text, "url": url, "anchor": anchor})
            continue
        for text, url in _INLINE_LINK_RE.findall(line):
            links.append({"text": text.strip(), "url": url, "anchor": line.strip()})
        line = _INLINE_LINK_RE.sub(lambda m: m.group(1), line)
        if line.strip():
            anchor = line.strip()
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)), links


def attach_links(chunks: list, links: list[dict[str, str]]) -> None:
    """Store on each chunk (``meta["links"]``) the links whose anchor line it contains."""
    for chunk in chunks:
        found = [
            {"text": link["text"], "url": link["url"]}
            for link in links
            if link["anchor"] and link["anchor"][:80] in chunk.text
        ]
        unique = list({(f["text"], f["url"]): f for f in found}.values())
        if unique:
            chunk.meta["links"] = unique


def _resolve(collection_dir: Path, relative: str) -> Path:
    """Resolve a collection-relative path; refuse excluded or escaping paths."""
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if not parts or ".." in parts or parts[0] in EXCLUDED_DIRS or parts[-1] in EXCLUDED_FILES:
        raise CollectionError(f"{relative!r} is not an allowed corpus file")
    return Path(collection_dir).joinpath(*parts)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_document(source: CollectionSource, collection_dir: Path) -> dict[str, Any]:
    """Build the document record for one source from its text copy, else its PDF."""
    if source.text_path and _resolve(collection_dir, source.text_path).exists():
        path = _resolve(collection_dir, source.text_path)
        front, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if front.get("id") not in (None, source.id):
            raise CollectionError(f"{path.name}: front matter id {front.get('id')} != {source.id}")
        representation = "text"
    elif source.pdf_path and _resolve(collection_dir, source.pdf_path).exists():
        path = _resolve(collection_dir, source.pdf_path)
        if source.sha256 and _sha256(path) != source.sha256:
            raise CollectionError(f"{path.name}: SHA-256 does not match sources.json")
        body = extract_pdf(path.read_bytes()).text
        representation = "pdf"
    else:
        raise CollectionError(f"{source.id}: neither text_path nor pdf_path exists")

    body, links = extract_links(body)
    if not body.strip():
        raise CollectionError(f"{source.id}: no text")
    detected = detect_language(body)
    if source.language != "en" or detected not in ("en", "unknown"):
        raise CollectionError(
            f"{source.id}: content language {source.language}/{detected}, English only"
        )
    return {
        "doc_id": source.id,
        "title": source.title,
        "url": source.source_url,
        "language": "en",
        "fetched_at": source.meta.get("accessed_at"),
        "representation": representation,
        "path": path.relative_to(collection_dir).as_posix(),
        "meta": {"source_id": source.id, **source.meta},
        "links": links,
        "text": body,
    }


def ingest_collection(collection_dir: Path, processed_dir: Path, chunker: Chunker) -> IngestReport:
    """Load every ``ingest: true`` source once, chunk it and write the JSONL outputs."""
    collection_dir = Path(collection_dir)
    report = IngestReport()
    for source in load_collection(collection_dir):
        if not source.ingest:
            logger.info("skipping %s (ingest=false)", source.id)
            continue
        try:
            report.documents.append(load_document(source, collection_dir))
        except CollectionError as exc:
            logger.error("skipping %s: %s", source.id, exc)
            report.failed.append((source.id, str(exc)))
    for doc in report.documents:
        chunks = chunker.chunk(doc)
        attach_links(chunks, doc.get("links", []))
        report.chunks.extend(chunks)
    write_jsonl(processed_dir / "documents.jsonl", report.documents)
    write_jsonl(processed_dir / "chunks.jsonl", (c.to_dict() for c in report.chunks))
    return report
