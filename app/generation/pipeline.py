"""Question -> (small talk | retrieval -> refusal or LLM answer) -> citations.

Build an ``AnswerPipeline`` once (models and the LLM client are loaded then) and call
``answer(question)`` for each question. ``answer(question, mode)`` at module level does the
same with a cached pipeline per mode.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from app.config import Settings, get_settings
from app.generation.llm_client import LLMClient
from app.generation.prompts import (
    CITATION_RETRY_NOTE,
    REFUSAL_TEXT,
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_response_type,
)
from app.generation.smalltalk import REPLIES, detect_smalltalk
from app.retrieval.base import Hit, Retriever
from app.retrieval.factory import Mode, get_retriever
from app.retrieval.rerank import RerankedRetriever

SNIPPET_CHARS = 200
_CITATION_RE = re.compile(r"\[([\d\s,;\-–]+)\]")
# Explicit requests for a German answer; everything else is answered in English.
_GERMAN_REQUEST_RE = re.compile(
    r"\bauf deutsch\b"
    r"|\b(answer|reply|respond|write|explain|tell me|translate)\b[^.?!]*\b(in|into) german\b"
    r"|\bin german,? please\b|\bplease\b[^.?!]*\bin german\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Citation:
    """A source the answer actually cites, under the number used in the answer text."""

    number: int
    title: str
    url: str
    snippet: str
    doc_id: str
    language: str


@dataclass(frozen=True)
class Source:
    """One cited document with every passage number the answer cites from it."""

    numbers: tuple[int, ...]
    doc_id: str
    title: str
    url: str
    language: str
    snippet: str  # from the first cited passage of this document


@dataclass
class Answer:
    """Result of one question."""

    question: str
    answer: str
    citations: list[Citation]
    refused: bool
    mode: str
    language: str
    best_score: float | None
    timings_ms: dict[str, float | None] = field(default_factory=dict)
    refusal_reason: str | None = None  # "no_hits" | "low_score" | "not_in_sources"
    model: str | None = None
    sources: list[Source] = field(default_factory=list)  # citations grouped by document
    # "answer" | "clarify" (asks for a missing detail) | "not_found" | "refused" | "smalltalk"
    response_type: str = "answer"
    retrieved: list[dict] = field(default_factory=list)  # [{chunk_id, doc_id, score}, ...]
    retried: bool = False  # the first LLM reply cited nothing and was asked again

    def to_dict(self) -> dict:
        """JSON-serialisable representation (for the API)."""
        return asdict(self)


# ------------------------------------------------------------------- helpers


def response_language(question: str) -> str:
    """English by default; "de" only if the user explicitly asks for a German answer."""
    return "de" if _GERMAN_REQUEST_RE.search(question) else "en"


def parse_citations(text: str, n_passages: int) -> list[int]:
    """Passage numbers cited in ``text`` ([1], [1, 3], [2][4], [1-3]), sorted, valid only."""
    found: set[int] = set()
    for group in _CITATION_RE.findall(text):
        for part in re.split(r"[,;]", group):
            bounds = [b for b in re.split(r"[-–]", part.strip()) if b.strip()]
            if not bounds or not all(b.strip().isdigit() for b in bounds):
                continue
            low, high = int(bounds[0]), int(bounds[-1])
            if len(bounds) > 2 or high < low or high - low >= n_passages:
                continue
            found.update(range(low, high + 1))
    return sorted(i for i in found if 1 <= i <= n_passages)


def group_sources(citations: list[Citation]) -> list[Source]:
    """One Source per document, ordered by its first citation number."""
    by_doc: dict[str, list[Citation]] = {}
    for citation in sorted(citations, key=lambda c: c.number):
        by_doc.setdefault(citation.doc_id, []).append(citation)
    return [
        Source(
            numbers=tuple(c.number for c in group),
            doc_id=group[0].doc_id,
            title=group[0].title,
            url=group[0].url,
            language=group[0].language,
            snippet=group[0].snippet,
        )
        for group in by_doc.values()
    ]


def limit_per_document(hits: list[Hit], k: int, cap: int) -> list[Hit]:
    """Best ``k`` hits keeping at most ``cap`` chunks per document (0 = no cap).

    Keeps one long page from filling every slot, so questions that need several sources
    (e.g. all four residences) can get them. If too few documents are left, the remaining
    slots are filled with the next best chunks regardless of the cap.
    """
    if cap <= 0:
        return hits[:k]
    chosen: list[Hit] = []
    per_doc: dict[str, int] = {}
    for hit in hits:
        if per_doc.get(hit.doc_id, 0) < cap:
            chosen.append(hit)
            per_doc[hit.doc_id] = per_doc.get(hit.doc_id, 0) + 1
        if len(chosen) == k:
            return chosen
    rest = [h for h in hits if h not in chosen]
    chosen += rest[: k - len(chosen)]
    return sorted(chosen, key=lambda h: -h.score)


def make_snippet(hit: Hit, max_chars: int = SNIPPET_CHARS) -> str:
    """Start of the chunk body (without the "title > section" header), cut at a word."""
    parts = hit.text.split("\n\n", 1)
    body = " ".join((parts[1] if len(parts) == 2 else hit.text).split())
    if len(body) <= max_chars:
        return body
    return body[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + " …"


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


# ------------------------------------------------------------------ pipeline


class AnswerPipeline:
    """Retriever + LLM client, created once and reused for every question."""

    def __init__(
        self,
        retriever: Retriever,
        llm: LLMClient,
        settings: Settings | None = None,
        mode: str | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.settings = settings or get_settings()
        self.mode = mode or retriever.name

    @classmethod
    def from_settings(
        cls, mode: Mode = "hybrid_rerank", settings: Settings | None = None
    ) -> AnswerPipeline:
        """Load the retriever (and its models) and the LLM client for ``mode``."""
        return cls(get_retriever(mode, settings), LLMClient.from_settings(settings), settings, mode)

    @property
    def reranked(self) -> bool:
        """True if scores are reranker probabilities (0-1), so the threshold applies."""
        return isinstance(self.retriever, RerankedRetriever)

    def retrieve(self, question: str) -> tuple[list[Hit], dict[str, float | None]]:
        """Top ``TOP_K_FINAL`` hits (at most ``MAX_CHUNKS_PER_DOC`` per document) and timings."""
        k = self.settings.top_k_final
        cap = self.settings.max_chunks_per_doc
        start = time.perf_counter()
        if isinstance(self.retriever, RerankedRetriever):
            candidates = self.retriever.inner.search(question, max(self.retriever.candidates, k))
            mid = time.perf_counter()
            ranked = self.retriever.rerank(question, candidates, len(candidates))
            end = time.perf_counter()
            timings = {"retrieval": _ms(mid - start), "reranking": _ms(end - mid)}
            return limit_per_document(ranked, k, cap), timings
        hits = self.retriever.search(question, k * 3 if cap else k)
        timings = {"retrieval": _ms(time.perf_counter() - start), "reranking": None}
        return limit_per_document(hits, k, cap), timings

    def answer(self, question: str) -> Answer:
        """Answer one question from the sources, or refuse without calling the LLM."""
        question = question.strip()
        if not question:
            raise ValueError("question is empty")
        start = time.perf_counter()
        language = response_language(question)

        smalltalk = detect_smalltalk(question)
        if smalltalk:
            return Answer(
                question, REPLIES[smalltalk], [], False, self.mode, "en", None,
                {"retrieval": None, "reranking": None, "generation": None,
                 "total": _ms(time.perf_counter() - start)},
                response_type="smalltalk",
            )  # fmt: skip

        hits, timings = self.retrieve(question)
        best = hits[0].score if hits else None
        retrieved = [
            {"chunk_id": h.chunk_id, "doc_id": h.doc_id, "score": round(h.score, 4)} for h in hits
        ]

        reason = None
        if not hits:
            reason = "no_hits"
        elif self.reranked and best < self.settings.refusal_threshold:
            reason = "low_score"
        if reason:
            timings["generation"] = None
            timings["total"] = _ms(time.perf_counter() - start)
            return Answer(
                question, REFUSAL_TEXT[language], [], True, self.mode, language, best,
                timings, refusal_reason=reason, response_type="refused", retrieved=retrieved,
            )  # fmt: skip

        gen_start = time.perf_counter()
        user_prompt = build_user_prompt(question, hits)
        result = self.llm.complete(SYSTEM_PROMPT, user_prompt)
        response_type, text = parse_response_type(result.text)
        cited = parse_citations(text, len(hits))
        retried = False
        if response_type in ("answer", "clarify") and not cited:
            # An uncited answer or a bare question ("What would you like to know?") breaks
            # the grounding rules; ask once more with an explicit correction.
            retried = True
            result = self.llm.complete(SYSTEM_PROMPT, f"{user_prompt}\n\n{CITATION_RETRY_NOTE}")
            response_type, text = parse_response_type(result.text)
            cited = parse_citations(text, len(hits))
        if response_type == "not_found" and cited:
            # Citing passages means something useful was found: a partial answer (which names
            # the missing part) is an answer, not a refusal with a "not found" banner.
            response_type = "answer"
        timings["generation"] = _ms(time.perf_counter() - gen_start)
        timings["total"] = _ms(time.perf_counter() - start)

        citations = [
            Citation(
                number=n,
                title=hits[n - 1].title,
                url=hits[n - 1].url,
                snippet=make_snippet(hits[n - 1]),
                doc_id=hits[n - 1].doc_id,
                language=hits[n - 1].language,
            )
            for n in cited
        ]
        not_found = response_type == "not_found"
        return Answer(
            question=question,
            answer=text,
            citations=citations,
            refused=not_found,
            mode=self.mode,
            language=language,
            best_score=best,
            timings_ms=timings,
            refusal_reason="not_in_sources" if not_found else None,
            model=result.model,
            sources=group_sources(citations),
            response_type=response_type,
            retrieved=retrieved,
            retried=retried,
        )


@lru_cache(maxsize=4)
def get_pipeline(mode: Mode = "hybrid_rerank") -> AnswerPipeline:
    """Process-wide pipeline per mode (models and client loaded on first use)."""
    return AnswerPipeline.from_settings(mode)


def answer(question: str, mode: Mode = "hybrid_rerank") -> Answer:
    """Answer ``question`` with the cached pipeline for ``mode``."""
    return get_pipeline(mode).answer(question)
