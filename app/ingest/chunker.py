"""Split cleaned documents into overlapping, sentence-aligned chunks.

Algorithm
1. Split the document into sections at Markdown headings (``#`` .. ``######``).
2. Split each section into sentences (never cutting inside one).
3. Greedily pack sentences into chunks of at most ``chunk_tokens`` tokens; the
   next chunk starts with the last sentences of the previous one (about
   ``overlap`` x ``chunk_tokens`` tokens) so context is not lost at the border.
4. Prefix every chunk with ``"<document title> > <section heading>"``.

Before step 2, small neighbouring sections under the same parent heading
(e.g. "Module Objective", "Literature" of one module) are merged into one
section labelled with the parent; each sub-heading stays in the text as its own
line. This avoids many tiny, low-information chunks.

A single "sentence" longer than the budget (e.g. a huge table row without
punctuation) is the only thing ever split mid-sentence, at word boundaries.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

TokenCounter = Callable[[str], int]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
MAX_HEADING_DEPTH = 2  # section labels keep only the innermost headings

# Abbreviations (lower-case, without the dot) after which a period does not end a sentence.
# Single letters ("z. B.", "e. g.") and dotted forms ("z.B.") are handled by rule.
_ABBREVIATIONS = frozenset(
    {
        "abs",
        "allg",
        "approx",
        "apr",
        "aug",
        "ave",
        "bzgl",
        "bzw",
        "ca",
        "corp",
        "dec",
        "dept",
        "dez",
        "dipl",
        "dr",
        "etc",
        "evtl",
        "exkl",
        "feb",
        "fig",
        "fr",
        "gem",
        "ggf",
        "ggfs",
        "hr",
        "incl",
        "inkl",
        "jan",
        "jh",
        "jul",
        "jun",
        "ltd",
        "max",
        "min",
        "mind",
        "mio",
        "mr",
        "mrd",
        "mrs",
        "ms",
        "mär",
        "nov",
        "nr",
        "oct",
        "okt",
        "prof",
        "sep",
        "sept",
        "sog",
        "st",
        "std",
        "str",
        "tel",
        "ua",
        "univ",
        "usw",
        "uvm",
        "vgl",
        "vs",
        "zb",
        "zzgl",
    }
)
# Candidate boundary: ., ! ? or … (plus closing quotes/brackets), whitespace, then a
# character that can start a sentence.
_BOUNDARY_RE = re.compile(r"[.!?…][\"'”’»)\]]*\s+(?=[\"'„“«(\[]?[A-ZÄÖÜ0-9])")
_WORD_BEFORE_RE = re.compile(r"(\S+)$")


@dataclass(frozen=True)
class Section:
    """A section label (e.g. ``"Visa > EU students"``) and the text lines under it.

    ``path`` is the full heading path; ``heading`` is its display label (the
    innermost ``MAX_HEADING_DEPTH`` headings).
    """

    heading: str
    lines: tuple[str, ...]
    path: tuple[str, ...] = ()

    @property
    def parent(self) -> tuple[str, ...]:
        """Heading path of the enclosing section (empty for top-level sections)."""
        return self.path[:-1]


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of text plus the metadata needed to cite it."""

    chunk_id: str
    doc_id: str
    title: str
    url: str
    language: str
    section: str
    text: str
    n_tokens: int
    meta: dict = field(default_factory=dict)  # source metadata (publisher, dates, period, ...)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return asdict(self)


# --------------------------------------------------------------------- sections


def split_sections(text: str, title: str = "") -> list[Section]:
    """Split Markdown-like text into sections at headings.

    The section heading is a short path: a heading directly followed by another
    heading (no text in between) becomes the parent of the next one, so an empty
    "Visa" heading followed by "EU students" yields ``"Visa > EU students"``.
    Only the innermost ``MAX_HEADING_DEPTH`` headings are kept in the label.
    A level-1 heading equal to the document title is ignored. Text before the
    first heading gets the heading ``""``. Sections without text are dropped.
    """
    stack: list[tuple[int, str]] = []
    lines: list[str] = []
    sections: list[Section] = []

    def flush() -> None:
        body = tuple(ln for ln in lines if ln.strip())
        if body:
            path = tuple(h for _, h in stack)
            sections.append(Section(_label(path), body, path))

    for raw in text.split("\n"):
        match = _HEADING_RE.match(raw.strip())
        if not match:
            lines.append(raw.strip())
            continue
        level, heading = len(match.group(1)), match.group(2).strip().rstrip(":")
        if level == 1 and heading.casefold() == title.strip().casefold():
            continue
        previous_heading_empty = bool(stack) and not any(ln.strip() for ln in lines)
        flush()
        lines = []
        keep_as_parent = previous_heading_empty and stack[-1][0] <= level
        if not keep_as_parent:
            while stack and stack[-1][0] >= level:
                stack.pop()
        stack.append((level, heading))
    flush()
    return sections


def _label(path: tuple[str, ...]) -> str:
    """Display label of a heading path: its innermost ``MAX_HEADING_DEPTH`` headings."""
    return " > ".join(path[-MAX_HEADING_DEPTH:])


# -------------------------------------------------------------------- sentences


def split_sentences(text: str) -> list[str]:
    """Split one paragraph into sentences (German/English aware).

    Periods after known abbreviations ("z. B.", "bzw.", "Dr.", "e.g."), single
    letters and 1-2 digit ordinals ("1. Oktober", "2. Semester") are not treated
    as sentence ends.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for match in _BOUNDARY_RE.finditer(text):
        end = match.start() + 1
        if text[match.start()] == "." and _is_abbreviation(text[start : match.start()]):
            continue
        sentence = text[start:end].strip()
        # keep closing quotes/brackets with the sentence they close
        closing = match.group(0)[1:].rstrip()
        sentence = (sentence + closing).strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _is_abbreviation(before: str) -> bool:
    match = _WORD_BEFORE_RE.search(before)
    if not match:
        return False
    word = match.group(1).lstrip("(\"'„“«[")
    bare = word.rstrip(".").lower()
    if not bare:
        return False
    if bare in _ABBREVIATIONS or (len(bare) == 1 and bare.isalpha()):
        return True
    if "." in bare:  # "z.B", "e.g", "u.a"
        return True
    return bare.isdigit() and len(bare) <= 2  # ordinal: "1. Oktober"


# --------------------------------------------------------------------- chunking


class Chunker:
    """Turns documents (dicts with doc_id, title, url, language, text) into chunks."""

    def __init__(
        self,
        count_tokens: TokenCounter,
        chunk_tokens: int = 350,
        overlap: float = 0.15,
        min_section_tokens: int | None = None,
    ) -> None:
        """``min_section_tokens``: sections smaller than this are merged with their
        siblings (default: a quarter of ``chunk_tokens``; 0 disables merging)."""
        if chunk_tokens < 20:
            raise ValueError("chunk_tokens must be at least 20")
        if not 0 <= overlap < 0.5:
            raise ValueError("overlap must be in [0, 0.5)")
        self.count_tokens = count_tokens
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = round(chunk_tokens * overlap)
        self.min_section_tokens = (
            chunk_tokens // 4 if min_section_tokens is None else min_section_tokens
        )

    def chunk(self, doc: Mapping[str, Any]) -> list[Chunk]:
        """Chunk one document. Returns an empty list if it has no text."""
        title = (doc.get("title") or "").strip()
        chunks: list[Chunk] = []
        sections = self.merge_small_sections(split_sections(doc.get("text", ""), title), title)
        context = (doc.get("context") or "").strip()
        for section in sections:
            header = _header(title, section.heading)
            if context and header:  # e.g. "Source: Studierendenwerk ... | Scope: Deggendorf"
                header = header[:-1] + context + "\n\n"
            budget = self._body_budget(header)
            for body in self._chunk_section(section, budget):
                text = header + body
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc['doc_id']}-{len(chunks):04d}",
                        doc_id=doc["doc_id"],
                        title=title,
                        url=doc.get("url", ""),
                        language=doc.get("language", "unknown"),
                        section=section.heading,
                        text=text,
                        n_tokens=self.count_tokens(text),
                        meta=dict(doc.get("meta") or {}),
                    )
                )
        return chunks

    def merge_small_sections(self, sections: list[Section], title: str = "") -> list[Section]:
        """Merge runs of consecutive sibling sections when one side is small.

        Neighbours are merged if they share the same non-empty parent heading, the
        running group or the next section is smaller than ``min_section_tokens``,
        and together they still fit in one chunk. A merged section is labelled
        with the parent; each sub-heading is kept as the first line of its part.
        """
        if self.min_section_tokens <= 0:
            return sections
        merged: list[Section] = []
        group: list[Section] = []
        group_tokens = 0
        for section in sections:
            tokens = self.count_tokens("\n".join((*section.path[-1:], *section.lines)))
            if group and self._can_merge(group, group_tokens, section, tokens, title):
                group.append(section)
                group_tokens += tokens
                continue
            if group:
                merged.append(_combine(group))
            group, group_tokens = [section], tokens
        if group:
            merged.append(_combine(group))
        return merged

    def _can_merge(
        self, group: list[Section], group_tokens: int, section: Section, tokens: int, title: str
    ) -> bool:
        parent = group[0].parent
        if not parent or section.parent != parent:
            return False
        if min(group_tokens, tokens) >= self.min_section_tokens:
            return False
        return group_tokens + tokens <= self._body_budget(_header(title, _label(parent)))

    def _body_budget(self, header: str) -> int:
        """Tokens left for the body once the ``title > section`` header is counted."""
        return max(self.chunk_tokens - self.count_tokens(header), self.chunk_tokens // 2)

    def _chunk_section(self, section: Section, budget: int) -> list[str]:
        """Pack the sentences of one section into chunk bodies of at most ``budget`` tokens."""
        units: list[tuple[str, int]] = []  # (sentence, paragraph index)
        for para_idx, line in enumerate(section.lines):
            for sentence in split_sentences(line):
                units.extend((piece, para_idx) for piece in self._split_oversized(sentence, budget))
        if not units:
            return []
        counts = [self.count_tokens(text) for text, _ in units]
        overlap = min(self.overlap_tokens, budget // 2)
        return [_join(units[w.start : w.stop]) for w in _pack(counts, budget, overlap)]

    def _split_oversized(self, sentence: str, budget: int) -> list[str]:
        """Return ``[sentence]``, or word-boundary pieces if it alone exceeds the budget."""
        if self.count_tokens(sentence) <= budget:
            return [sentence]
        pieces: list[str] = []
        current: list[str] = []
        for word in sentence.split():
            candidate = " ".join([*current, word])
            if current and self.count_tokens(candidate) > budget:
                pieces.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            pieces.append(" ".join(current))
        return pieces


def _header(title: str, heading: str) -> str:
    """Chunk prefix ``"<title> > <section>"`` followed by a blank line."""
    prefix = f"{title} > {heading}" if heading else title
    return f"{prefix}\n\n" if prefix else ""


def _combine(group: list[Section]) -> Section:
    """Turn a run of sibling sections into one section labelled with their parent."""
    if len(group) == 1:
        return group[0]
    parent = group[0].parent
    lines = tuple(line for sec in group for line in (sec.path[-1], *sec.lines))
    return Section(_label(parent), lines, parent)


def _pack(counts: list[int], budget: int, overlap: int) -> list[range]:
    """Greedy sliding windows over unit token counts.

    Each window holds as many units as fit in ``budget``; the next window starts
    with trailing units of the previous one totalling at most ``overlap`` tokens,
    and always adds at least one new unit.
    """
    windows: list[range] = []
    start, n = 0, len(counts)
    while start < n:
        end, total = start, 0
        while end < n and total + counts[end] <= budget:
            total += counts[end]
            end += 1
        end = max(end, start + 1)  # unit larger than budget (cannot happen after splitting)
        windows.append(range(start, end))
        if end >= n:
            break
        back, carried = end, 0
        while back - 1 > start and carried + counts[back - 1] <= overlap:
            back -= 1
            carried += counts[back]
        while back < end and carried + counts[end] > budget:  # make room for new content
            carried -= counts[back]
            back += 1
        start = back
    return windows


def _join(units: list[tuple[str, int]]) -> str:
    """Join sentences with spaces inside a paragraph and newlines between paragraphs."""
    out: list[str] = []
    prev_para: int | None = None
    for text, para in units:
        if out:
            out.append(" " if para == prev_para else "\n")
        out.append(text)
        prev_para = para
    return "".join(out)


# ---------------------------------------------------------------- token counters


def whitespace_token_counter(text: str) -> int:
    """Cheap approximation: number of whitespace-separated words (used in tests)."""
    return len(text.split())


@lru_cache(maxsize=2)
def hf_token_counter(model_name: str) -> TokenCounter:
    """Token counter using the embedding model's own tokenizer (loaded once, cached)."""
    from transformers import AutoTokenizer  # heavy import; only when actually needed

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.model_max_length = 10**9  # we only count tokens; silence the >512 warning

    def count(text: str) -> int:
        return len(tokenizer(text, add_special_tokens=False)["input_ids"])

    return count
