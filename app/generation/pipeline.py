"""Question -> retrieval -> (refusal or LLM answer) -> citations.

Build an ``AnswerPipeline`` once (models and the LLM client are loaded then) and call
``answer(question)`` for each question. ``answer(question, mode)`` at module level does the
same with a cached pipeline per mode.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from langdetect import DetectorFactory, LangDetectException, detect_langs

from app.config import Settings, get_settings
from app.generation.llm_client import LLMClient
from app.generation.prompts import REFUSAL_TEXT, SYSTEM_PROMPT, build_user_prompt
from app.retrieval.base import Hit, Retriever
from app.retrieval.factory import Mode, get_retriever
from app.retrieval.rerank import RerankedRetriever

DetectorFactory.seed = 0  # reproducible langdetect results

SNIPPET_CHARS = 200
_CITATION_RE = re.compile(r"\[([\d\s,;\-–]+)\]")
_WORD_RE = re.compile(r"[^\W\d_]+")
_GERMAN_WORDS = (
    "wie was wo wann warum wieso welche welcher welches wer ich ist sind der die das den dem "
    "und oder muss müssen kann darf brauche gibt es mein meine mich mir für nicht bei mit "
    "eine ein einen zum zur im auf"
)
_ENGLISH_WORDS = (
    "how what where when why which who i is are the and or must can may do does need my me "
    "for not with a an to of at on"
)
_GERMAN_HINTS = frozenset(_GERMAN_WORDS.split())
_ENGLISH_HINTS = frozenset(_ENGLISH_WORDS.split())


@dataclass(frozen=True)
class Citation:
    """A source the answer actually cites, under the number used in the answer text."""

    number: int
    title: str
    url: str
    snippet: str


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
    refusal_reason: str | None = None  # "no_hits" | "low_score" | "no_citations"
    model: str | None = None

    def to_dict(self) -> dict:
        """JSON-serialisable representation (for the API)."""
        return asdict(self)


# ------------------------------------------------------------------- helpers


def question_language(question: str) -> str:
    """Return "de" or "en" for a (possibly very short) question; English if unsure."""
    words = _WORD_RE.findall(question.lower())
    german = sum(w in _GERMAN_HINTS for w in words) + any(c in question.lower() for c in "äöüß")
    english = sum(w in _ENGLISH_HINTS for w in words)
    if german != english:
        return "de" if german > english else "en"
    try:
        probs = {c.lang: c.prob for c in detect_langs(question)}
    except LangDetectException:
        return "en"
    return "de" if probs.get("de", 0.0) > probs.get("en", 0.0) else "en"


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
        """Top ``TOP_K_FINAL`` hits plus retrieval/reranking times in ms."""
        k = self.settings.top_k_final
        start = time.perf_counter()
        if isinstance(self.retriever, RerankedRetriever):
            candidates = self.retriever.inner.search(question, max(self.retriever.candidates, k))
            mid = time.perf_counter()
            hits = self.retriever.rerank(question, candidates, k)
            end = time.perf_counter()
            return hits, {"retrieval": _ms(mid - start), "reranking": _ms(end - mid)}
        hits = self.retriever.search(question, k)
        return hits, {"retrieval": _ms(time.perf_counter() - start), "reranking": None}

    def answer(self, question: str) -> Answer:
        """Answer one question from the sources, or refuse without calling the LLM."""
        question = question.strip()
        if not question:
            raise ValueError("question is empty")
        start = time.perf_counter()
        language = question_language(question)
        hits, timings = self.retrieve(question)
        best = hits[0].score if hits else None

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
                timings, refusal_reason=reason,
            )  # fmt: skip

        gen_start = time.perf_counter()
        result = self.llm.complete(SYSTEM_PROMPT, build_user_prompt(question, hits))
        timings["generation"] = _ms(time.perf_counter() - gen_start)
        timings["total"] = _ms(time.perf_counter() - start)

        cited = parse_citations(result.text, len(hits))
        citations = [
            Citation(n, hits[n - 1].title, hits[n - 1].url, make_snippet(hits[n - 1]))
            for n in cited
        ]
        return Answer(
            question=question,
            answer=result.text,
            citations=citations,
            refused=not citations,
            mode=self.mode,
            language=language,
            best_score=best,
            timings_ms=timings,
            refusal_reason=None if citations else "no_citations",
            model=result.model,
        )


@lru_cache(maxsize=4)
def get_pipeline(mode: Mode = "hybrid_rerank") -> AnswerPipeline:
    """Process-wide pipeline per mode (models and client loaded on first use)."""
    return AnswerPipeline.from_settings(mode)


def answer(question: str, mode: Mode = "hybrid_rerank") -> Answer:
    """Answer ``question`` with the cached pipeline for ``mode``."""
    return get_pipeline(mode).answer(question)
