"""Keyword retrieval with BM25 (rank_bm25)."""

from __future__ import annotations

import pickle
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.retrieval.base import ChunkStore, Hit, Retriever, StaleIndexError

BM25_FILE = "bm25.pkl"
_FORMAT_VERSION = 1

# Unicode letters and digits: keeps ä ö ü ß and numbers ("§ 12" -> "12").
_TOKEN_RE = re.compile(r"[^\W_]+")

STOPWORDS = frozenset(
    """
    der die das den dem des ein eine einer eines einem einen und oder aber auch als am an auf
    aus bei bis da dass du er es für ist im in ins mit nach nicht noch nur ob sich sie sind so
    über um vom von vor was wie wir wird werden zu zum zur ich ihr ihre ihr kann können muss
    müssen hat haben sein dein deine ihnen man wenn welche welcher hier dort dann sowie bzw
    the a an and or but of to in on at by for with from as is are was were be been being it its
    this that these those i you he she we they my your our their do does did can could should
    would will shall may might must have has had not no if then than so how what which who
    whom when where why there here into about after before all any each also only up out
    """.split()  # noqa: SIM905 - easier to read and edit than a list literal
)


def tokenize(text: str) -> list[str]:
    """Lowercase, split on anything that is not a letter or digit, drop stopwords."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class BM25Retriever(Retriever):
    """BM25 over the full chunk text (including the ``title > section`` prefix)."""

    name = "bm25"

    def __init__(self, store: ChunkStore, bm25: BM25Okapi, chunk_ids: list[str]) -> None:
        self.store = store
        self.bm25 = bm25
        self.chunk_ids = chunk_ids

    @classmethod
    def build(cls, store: ChunkStore) -> BM25Retriever:
        """Build the BM25 index for all chunks in ``store``."""
        if not len(store):
            raise ValueError("cannot build a BM25 index over zero chunks")
        chunk_ids = [c["chunk_id"] for c in store.chunks]
        corpus = [tokenize(c["text"]) for c in store.chunks]
        return cls(store, BM25Okapi(corpus), chunk_ids)

    def search(self, query: str, k: int) -> list[Hit]:
        """Top-``k`` chunks by BM25 score; chunks sharing no query term are left out."""
        tokens = tokenize(query)
        if not tokens or k <= 0:
            return []
        scores = self.bm25.get_scores(tokens)
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = sorted(top, key=lambda i: (-scores[i], self.chunk_ids[i]))
        return [self.store.hit(self.chunk_ids[i], scores[i]) for i in top if scores[i] > 0]

    def save(self, index_dir: Path) -> Path:
        """Pickle the index to ``index_dir/bm25.pkl``."""
        index_dir.mkdir(parents=True, exist_ok=True)
        path = index_dir / BM25_FILE
        payload = {"version": _FORMAT_VERSION, "chunk_ids": self.chunk_ids, "bm25": self.bm25}
        with path.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        return path

    @classmethod
    def load(cls, index_dir: Path, store: ChunkStore) -> BM25Retriever:
        """Load a pickled index. Only load files written by :meth:`save` (pickle is unsafe)."""
        with (index_dir / BM25_FILE).open("rb") as f:
            payload = pickle.load(f)  # noqa: S301 - our own index file
        if payload.get("version") != _FORMAT_VERSION:
            raise StaleIndexError("BM25 index format changed; rebuild the index")
        missing = [cid for cid in payload["chunk_ids"] if cid not in store]
        if missing or len(payload["chunk_ids"]) != len(store):
            raise StaleIndexError("BM25 index does not match chunks.jsonl; rebuild the index")
        return cls(store, payload["bm25"], payload["chunk_ids"])
