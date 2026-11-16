"""End-to-end ingestion: sources.yaml -> raw files -> documents.jsonl -> chunks.jsonl."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app.ingest.chunker import Chunk, Chunker
from app.ingest.extract import Extracted, extract_html, extract_pdf, remove_repeated_lines
from app.ingest.fetcher import FetchError, PoliteFetcher, looks_like_block_page
from app.ingest.jsonl import read_jsonl, write_jsonl
from app.ingest.language import detect_language
from app.ingest.sources import Source

logger = logging.getLogger(__name__)


@dataclass
class IngestReport:
    """What an ingestion run produced, plus the URLs that failed and why."""

    documents: list[dict] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary for the console."""
        langs = Counter(d["language"] for d in self.documents)
        n = len(self.chunks)
        avg_tokens = sum(c.n_tokens for c in self.chunks) / n if n else 0.0
        avg_chars = sum(len(c.text) for c in self.chunks) / n if n else 0.0
        lines = [
            "=== Ingestion summary ===",
            f"Documents: {len(self.documents)}"
            + (f"  ({', '.join(f'{k}: {v}' for k, v in sorted(langs.items()))})" if langs else ""),
            f"Chunks:    {n}",
            f"Avg chunk: {avg_tokens:.0f} tokens / {avg_chars:.0f} characters",
            f"Failed:    {len(self.failed)}",
        ]
        lines += [f"  - {url}: {reason}" for url, reason in self.failed]
        return "\n".join(lines)


def run_ingest(
    sources: list[Source],
    raw_dir: Path,
    processed_dir: Path,
    fetcher: PoliteFetcher,
    chunker: Chunker,
    refresh: bool = False,
) -> IngestReport:
    """Download (or reuse cached) sources, extract text, chunk, and write the JSONL outputs."""
    report = IngestReport()
    extracted: list[tuple[Source, Extracted, str]] = []  # (source, text, fetched_at)

    for source in sources:
        try:
            content, fetched_at = _get_raw(source, raw_dir, fetcher, refresh)
            result = _extract(source, content)
        except (FetchError, ValueError) as exc:
            logger.error("skipping %s: %s", source.url, exc)
            report.failed.append((source.url, str(exc)))
            continue
        if not result.text.strip():
            logger.error("skipping %s: no text extracted", source.url)
            report.failed.append((source.url, "no text extracted"))
            continue
        extracted.append((source, result, fetched_at))

    _remove_site_boilerplate(extracted)

    for source, result, fetched_at in extracted:
        report.documents.append(
            {
                "doc_id": source.doc_id,
                "title": source.title or result.title or source.url,
                "url": source.url,
                "language": detect_language(result.text),
                "fetched_at": fetched_at,
                "text": result.text,
            }
        )
    for doc in report.documents:
        report.chunks.extend(chunker.chunk(doc))

    write_jsonl(processed_dir / "documents.jsonl", report.documents)
    write_jsonl(processed_dir / "chunks.jsonl", (c.to_dict() for c in report.chunks))
    return report


def rechunk(processed_dir: Path, chunker: Chunker) -> IngestReport:
    """Re-chunk the existing documents.jsonl (no downloading) and rewrite chunks.jsonl."""
    report = IngestReport(documents=list(read_jsonl(processed_dir / "documents.jsonl")))
    for doc in report.documents:
        report.chunks.extend(chunker.chunk(doc))
    write_jsonl(processed_dir / "chunks.jsonl", (c.to_dict() for c in report.chunks))
    return report


def _get_raw(
    source: Source, raw_dir: Path, fetcher: PoliteFetcher, refresh: bool
) -> tuple[bytes, str]:
    """Return (raw bytes, fetched_at), downloading only if not cached or ``refresh``."""
    raw_path = raw_dir / f"{source.doc_id}.{source.type}"
    meta_path = raw_dir / f"{source.doc_id}.meta.json"
    if not refresh and raw_path.exists() and meta_path.exists():
        content = raw_path.read_bytes()
        if looks_like_block_page(content):  # cached by an older version; never reuse it
            raw_path.unlink()
            meta_path.unlink()
        else:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            logger.info("using cached %s", raw_path.name)
            return content, meta["fetched_at"]

    logger.info("downloading %s", source.url)
    result = fetcher.fetch(source.url)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(result.content)
    meta = {
        "url": source.url,
        "final_url": result.final_url,
        "content_type": result.content_type,
        "fetched_at": result.fetched_at,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return result.content, result.fetched_at


def _extract(source: Source, content: bytes) -> Extracted:
    """Extract text according to the declared type, checking the bytes really match it."""
    is_pdf = content.lstrip()[:5] == b"%PDF-"
    if source.type == "pdf":
        if not is_pdf:
            raise ValueError("declared as pdf but the response is not a PDF")
        return extract_pdf(content)
    if is_pdf:
        raise ValueError("declared as html but the response is a PDF")
    return extract_html(content, url=source.url)


def _remove_site_boilerplate(items: list[tuple[Source, Extracted, str]]) -> None:
    """Drop lines repeated across many HTML pages of the same host (shared footers etc.)."""
    by_host: dict[str, list[int]] = defaultdict(list)
    for i, (source, _, _) in enumerate(items):
        if source.type == "html":
            by_host[urlparse(source.url).netloc].append(i)
    for indices in by_host.values():
        cleaned = remove_repeated_lines(items[i][1].text for i in indices)
        for i, text in zip(indices, cleaned, strict=True):
            items[i][1].text = text
