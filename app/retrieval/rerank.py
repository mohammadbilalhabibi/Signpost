"""Cross-encoder reranking on top of any retriever."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from app.retrieval.base import Hit, Retriever


class CrossEncoderLike(Protocol):
    """The subset of sentence-transformers' CrossEncoder used here (lets tests pass a fake)."""

    def predict(self, sentences: list[tuple[str, str]], **kwargs) -> np.ndarray: ...


def to_probability(scores: np.ndarray) -> np.ndarray:
    """Map raw logits to 0-1 with a sigmoid; values already in [0, 1] are kept as they are."""
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    if scores.size and (scores.min() < 0.0 or scores.max() > 1.0):
        scores = 1.0 / (1.0 + np.exp(-scores))
    return scores


class RerankedRetriever(Retriever):
    """Re-scores the inner retriever's top candidates with a cross-encoder.

    Returns ``min(k, number of candidates)`` hits with the reranker score (0-1), so the
    answer pipeline can ask for k=5 and the evaluation for k=10.
    """

    def __init__(
        self,
        inner: Retriever,
        cross_encoder: CrossEncoderLike,
        candidates: int = 20,
        batch_size: int = 16,
    ) -> None:
        self.inner = inner
        self.cross_encoder = cross_encoder
        self.candidates = candidates
        self.batch_size = batch_size
        self.name = f"{inner.name}_rerank"

    def search(self, query: str, k: int) -> list[Hit]:
        """Rerank ``max(candidates, k)`` inner hits and return the best ``k``."""
        if k <= 0:
            return []
        return self.rerank(query, self.inner.search(query, max(self.candidates, k)), k)

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]:
        """Score ``hits`` with the cross-encoder and return the best ``k`` (score 0-1)."""
        if k <= 0 or not hits:
            return []
        raw = self.cross_encoder.predict(
            [(query, h.text) for h in hits], batch_size=self.batch_size, show_progress_bar=False
        )
        scores = to_probability(raw)
        order = sorted(range(len(hits)), key=lambda i: (-scores[i], i))[:k]
        return [Hit(**{**hits[i].__dict__, "score": float(scores[i])}) for i in order]
