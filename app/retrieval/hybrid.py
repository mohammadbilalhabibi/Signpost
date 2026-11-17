"""Hybrid retrieval: Reciprocal Rank Fusion of several retrievers (dense + BM25)."""

from __future__ import annotations

from collections.abc import Sequence

from app.retrieval.base import Hit, Retriever


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], k: int = 60
) -> list[tuple[str, float]]:
    """Fuse ranked id lists: ``score(id) = sum over lists of 1 / (k + rank)``, rank from 1.

    Ties are broken by the best single rank, then by id, so results are deterministic.
    """
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best_rank[item] = min(best_rank.get(item, rank), rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], best_rank[kv[0]], kv[0]))


class HybridRetriever(Retriever):
    """Takes the top ``candidates`` of each retriever and merges them with RRF."""

    name = "hybrid"

    def __init__(
        self, retrievers: Sequence[Retriever], candidates: int = 20, rrf_k: int = 60
    ) -> None:
        if not retrievers:
            raise ValueError("HybridRetriever needs at least one retriever")
        self.retrievers = list(retrievers)
        self.candidates = candidates
        self.rrf_k = rrf_k

    def search(self, query: str, k: int) -> list[Hit]:
        """Top-``k`` hits by RRF score (each retriever asked for ``max(candidates, k)``)."""
        if k <= 0:
            return []
        n = max(self.candidates, k)
        hits_by_id: dict[str, Hit] = {}
        rankings: list[list[str]] = []
        for retriever in self.retrievers:
            hits = retriever.search(query, n)
            rankings.append([h.chunk_id for h in hits])
            for h in hits:
                hits_by_id.setdefault(h.chunk_id, h)
        fused = reciprocal_rank_fusion(rankings, k=self.rrf_k)[:k]
        return [_with_score(hits_by_id[cid], score) for cid, score in fused]


def _with_score(hit: Hit, score: float) -> Hit:
    return Hit(**{**hit.__dict__, "score": float(score)})
