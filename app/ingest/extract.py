"""Turn raw HTML/PDF bytes into clean, Markdown-like text with ``#`` headings.

Output format (consumed by the chunker): headings as ``#``..``######`` lines,
paragraphs / list items / table rows separated by newlines.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import median

import pymupdf
import trafilatura

_COOKIE_RE = re.compile(r"\bcookie", re.IGNORECASE)
_COOKIE_CONTEXT_RE = re.compile(
    r"akzept|accept|zustimm|einwillig|consent|einstellung|settings|we use|wir verwenden|"
    r"datenschutz|privacy",
    re.IGNORECASE,
)
_BOILERPLATE_LINES = {
    "back to top",
    "nach oben",
    "zurück nach oben",
    "seite drucken",
    "print page",
    "share",
    "teilen",
    "drucken",
    "print",
    "skip to content",
    "zum inhalt springen",
}
_PAGE_NUMBER_RE = re.compile(r"^(seite|page)?\s*\d{1,4}(\s*(von|of|/)\s*\d{1,4})?$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass
class Extracted:
    """Result of text extraction."""

    text: str
    title: str | None = None
    meta: dict[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------------- HTML


def extract_html(content: bytes, url: str | None = None) -> Extracted:
    """Extract main content of an HTML page with trafilatura (drops nav, footer, ads).

    Uses precision mode first and falls back to recall mode if that finds almost nothing.
    """
    options = dict(
        url=url,
        output_format="markdown",
        include_formatting=True,
        include_links=False,
        include_images=False,
        include_comments=False,
        include_tables=True,
        # trafilatura's deduplication keeps a cache across documents, which silently drops
        # text seen on earlier pages; cross-page boilerplate is removed in the pipeline.
        deduplicate=False,
    )
    text = trafilatura.extract(content, favor_precision=True, **options) or ""
    if len(text) < 200:  # precision mode sometimes discards short or list-like pages
        fallback = trafilatura.extract(content, favor_recall=True, **options) or ""
        text = fallback if len(fallback) > len(text) else text
    metadata = trafilatura.extract_metadata(content, default_url=url)
    title = metadata.title.strip() if metadata and metadata.title else None
    return Extracted(text=clean_text(text), title=title)


# ------------------------------------------------------------------------------ PDF


@dataclass
class _Row:
    page: int
    y0: float
    y1: float
    size: float
    bold: bool
    text: str


_PARAGRAPH_SIGN_RE = re.compile(r"^§+\s*\d+[a-z]?$")  # "§ 4" on its own line
_TOC_RE = re.compile(r"(\.\s?){5,}\s*\d*\s*$|…{2,}\s*\d*\s*$")
_LIST_MARKER_RE = re.compile(r"^([-•▪●◦*–]|\(?\d{1,2}[.)]|\(?[a-z][.)])$")
_LIST_ITEM_RE = re.compile(r"^([-•▪●◦*–]|\(?\d{1,2}[.)]|\(?[a-z][.)])\s")


def extract_pdf(content: bytes) -> Extracted:
    """Extract text from a PDF with PyMuPDF.

    Spans are regrouped into visual rows (so table cells stay on one line).
    Rows in a clearly larger font, or short all-bold rows (e.g. "§ 4
    Prüfungskommission"), become ``#`` headings; multi-line headings are merged.
    Wrapped lines are re-joined into paragraphs (undoing hyphenation). Running
    headers/footers, page numbers, table-of-contents rows and superscript
    footnote/sentence numbers are dropped.
    """
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        rows = [row for page in doc for row in _page_rows(page)]
        page_count = doc.page_count
        meta_title = (doc.metadata or {}).get("title") or ""

    rows = [r for r in _drop_running_headers(rows, page_count) if not _TOC_RE.search(r.text)]
    if not rows:
        return Extracted(text="", title=None)

    body_size = _body_font_size(rows)
    # Forms or annexes may use a bigger body font than the rest of the document,
    # so a row must also stand out from the text on its own page.
    by_page: dict[int, list[_Row]] = {}
    for r in rows:
        by_page.setdefault(r.page, []).append(r)
    page_body = {page: _body_font_size(page_rows) for page, page_rows in by_page.items()}
    is_heading = [
        _is_heading(r, max(body_size, page_body[r.page]), page_body[r.page]) for r in rows
    ]
    big_sizes = sorted(
        {r.size for r, h in zip(rows, is_heading, strict=True) if h and r.size >= body_size * 1.2},
        reverse=True,
    )
    level_of = {size: min(i + 1, 6) for i, size in enumerate(big_sizes)}
    bold_level = min(len(big_sizes) + 1, 6)  # body-size bold headings sit below all others

    lines: list[str] = []
    prev: _Row | None = None
    prev_heading = False
    for row, heading in zip(rows, is_heading, strict=True):
        if heading:
            if prev_heading and prev is not None and _same_heading(prev, row):
                lines[-1] = _join_wrapped(lines[-1], row.text)  # multi-line heading
            else:
                level = level_of.get(row.size, bold_level)
                lines.append(f"{'#' * level} {row.text}")
        elif prev is not None and not prev_heading and lines and _continues_paragraph(prev, row):
            lines[-1] = _join_wrapped(lines[-1], row.text)
        else:
            lines.append(row.text)
        prev, prev_heading = row, heading

    title = None
    headings = [(len(m.group(1)), m.group(2)) for ln in lines if (m := _HEADING_RE.match(ln))]
    first_heading = min(headings, key=lambda h: h[0])[1] if headings else None  # top level
    # InDesign/Word often leave file names as metadata title; ignore those.
    if meta_title and not re.search(r"\.(indd|docx?|pdf|pptx?)$|^untitled", meta_title, re.I):
        title = meta_title.strip()
    elif first_heading:
        title = first_heading
    return Extracted(text=clean_text("\n".join(lines)), title=title)


def _page_rows(page: pymupdf.Page) -> list[_Row]:
    """Group the spans of one page into visual rows, ordered top-to-bottom, left-to-right.

    Whitespace-only spans are kept as word separators (some PDFs store the space
    between words as its own span) but never define a row's size or position.
    """
    spans = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].replace("­", "")
                if text:
                    bold = bool(span["flags"] & 16) or "bold" in span["font"].lower()
                    spans.append((span["bbox"], span["size"], text, bold))
    spans.sort(key=lambda s: ((s[0][1] + s[0][3]) / 2, s[0][0]))

    groups: list[list[tuple]] = []
    for span in spans:
        mid = (span[0][1] + span[0][3]) / 2
        if groups:
            last = groups[-1]
            last_mid = sum((s[0][1] + s[0][3]) / 2 for s in last) / len(last)
            if abs(mid - last_mid) <= max(2.0, 0.4 * span[1]):
                last.append(span)
                continue
        groups.append([span])

    rows = []
    for group in groups:
        group.sort(key=lambda s: s[0][0])
        visible = [s for s in group if s[2].strip()]
        if not visible:
            continue
        row_size = max(s[1] for s in visible)
        # Superscript footnote / sentence numbers ("BayHIG¹", "²Als ...") are noise.
        group = [s for s in group if not (s[2].strip().isdigit() and s[1] < 0.8 * row_size)]
        visible = [s for s in group if s[2].strip()]
        if not visible:
            continue
        parts: list[str] = []
        prev_x1: float | None = None
        for bbox, size, text, _ in group:
            if not text.strip():
                parts.append(" ")
                continue
            if prev_x1 is not None:
                gap = bbox[0] - prev_x1
                last_cell = "".join(parts).rsplit(" | ", 1)[-1].strip()
                if gap > 3 * size and not _LIST_MARKER_RE.match(last_cell):
                    parts.append(" | ")  # wide gap: new table cell / column
                elif gap > 0.15 * size:
                    parts.append(" ")
            parts.append(text)
            prev_x1 = bbox[2]
        text = re.sub(r"\s+", " ", "".join(parts)).strip()
        text = re.sub(r"(\s*\|\s*)+", " | ", text).strip(" |")
        if not text:
            continue
        alpha_spans = [s for s in visible if any(c.isalpha() for c in s[2])] or visible
        rows.append(
            _Row(
                page=page.number,
                y0=min(s[0][1] for s in visible),
                y1=max(s[0][3] for s in visible),
                size=round(row_size, 1),
                bold=all(s[3] for s in alpha_spans),
                text=text,
            )
        )
    return rows


def _normalize_for_repeat(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


def _drop_running_headers(rows: list[_Row], page_count: int) -> list[_Row]:
    """Remove page numbers and rows that occur on at least half of the pages."""
    rows = [r for r in rows if not _PAGE_NUMBER_RE.match(r.text)]
    if page_count < 3:
        return rows
    pages_per_text: dict[str, set[int]] = {}
    for r in rows:
        # Rows with hardly any letters ("§ 4", "1.") look alike once digits are masked.
        if sum(c.isalpha() for c in r.text) >= 4:
            pages_per_text.setdefault(_normalize_for_repeat(r.text), set()).add(r.page)
    repeated = {t for t, pages in pages_per_text.items() if len(pages) >= max(3, page_count / 2)}
    return [r for r in rows if _normalize_for_repeat(r.text) not in repeated]


def _body_font_size(rows: list[_Row]) -> float:
    """Most common font size weighted by text length (= the body text size)."""
    weights: Counter[float] = Counter()
    for r in rows:
        weights[r.size] += len(r.text)
    return weights.most_common(1)[0][0] if weights else median(r.size for r in rows)


def _is_heading(row: _Row, body_size: float, page_body_size: float | None = None) -> bool:
    """Large-font rows, or short all-bold rows at (at least) body size, are headings.

    ``body_size`` is the reference for "large"; ``page_body_size`` (default: the
    same) is the body size of the row's own page, used for the bold rule.
    """
    page_body_size = body_size if page_body_size is None else page_body_size
    looks_like_title = (
        len(row.text) <= 120
        and "|" not in row.text
        and not row.text.endswith((".", ",", ";", ":"))
        and (any(c.isalpha() for c in row.text) or _PARAGRAPH_SIGN_RE.match(row.text))
    )
    if not looks_like_title:
        return False
    if row.size >= body_size * 1.2:
        return True
    return (
        row.bold
        and row.size >= page_body_size - 0.25
        and len(row.text) <= 100
        and not row.text.startswith(("•", "▪", "●", "◦", "-", "–", "*"))  # bold bullet point
    )


def _same_heading(prev: _Row, row: _Row) -> bool:
    """True if two consecutive heading rows are lines of one multi-line heading."""
    return (
        prev.page == row.page
        and abs(prev.size - row.size) < 0.5
        and prev.bold == row.bold
        and -0.5 * row.size <= row.y0 - prev.y1 <= 1.2 * row.size
    )


def _continues_paragraph(prev: _Row, row: _Row) -> bool:
    """True if ``row`` is the wrapped continuation of the paragraph ending in ``prev``."""
    if prev.page != row.page or "|" in prev.text or "|" in row.text:
        return False
    if abs(prev.size - row.size) > 0.5 or _LIST_ITEM_RE.match(row.text):
        return False
    gap = row.y0 - prev.y1  # bounding boxes of adjacent lines often overlap slightly
    return -0.5 * row.size <= gap <= 0.8 * row.size and not prev.text.endswith(":")


def _join_wrapped(left: str, right: str) -> str:
    """Join two wrapped lines, undoing end-of-line hyphenation ("Aufent-" + "halt")."""
    if re.search(r"[a-zäöüß]-$", left) and right[:1].islower():
        return left[:-1] + right
    return f"{left} {right}"


# -------------------------------------------------------------------------- cleanup


def clean_text(text: str) -> str:
    """Normalise whitespace and drop boilerplate lines (cookie banners, 'back to top', ...)."""
    text = text.replace(" ", " ").replace("​", "").replace("\r", "")
    out: list[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)  # drop Markdown bold markers
        line = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>])", r"\1", line)  # undo MD escapes
        line = re.sub(r"(?<!\w)\*(\S.*?\S)\*(?!\w)", r"\1", line)
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if _is_boilerplate(line):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _is_boilerplate(line: str) -> bool:
    plain = _HEADING_RE.sub(r"\2", line).strip(" .:-|").lower()
    if plain in _BOILERPLATE_LINES:
        return True
    return bool(len(line) < 400 and _COOKIE_RE.search(line) and _COOKIE_CONTEXT_RE.search(line))


def remove_repeated_lines(texts: Iterable[str], min_docs: int = 3, share: float = 0.5) -> list[str]:
    """Remove lines that occur in many documents (e.g. footers repeated on every page of a site).

    A line is dropped if it appears in at least ``min_docs`` documents and in at
    least ``share`` of all given documents. Call this per website (host).
    """
    texts = list(texts)
    doc_freq: Counter[str] = Counter()
    for text in texts:
        doc_freq.update({ln.strip() for ln in text.split("\n") if ln.strip()})
    threshold = max(min_docs, share * len(texts))
    repeated = {ln for ln, n in doc_freq.items() if n >= threshold}
    if not repeated:
        return texts
    return [
        clean_text("\n".join(ln for ln in text.split("\n") if ln.strip() not in repeated))
        for text in texts
    ]
