"""Dense retrieval: multilingual-e5 embeddings in a FAISS inner-product index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import faiss
import numpy as np

from app.retrieval.base import ChunkStore, Hit, Retriever, StaleIndexError

FAISS_FILE = "dense.faiss"
IDS_FILE = "dense_ids.json"

PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "


class Encoder(Protocol):
    """The subset of SentenceTransformer used here (lets tests pass a fake)."""

    def encode(self, sentences: list[str], **kwargs) -> np.ndarray: ...


def embed(encoder: Encoder, texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed texts as L2-normalised float32 rows (cosine similarity = inner product)."""
    vectors = encoder.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 100,
    )
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)  # no-op for real e5, safety for fakes


class DenseRetriever(Retriever):
    """Cosine-similarity search over e5 passage embeddings (FAISS IndexFlatIP)."""

    name = "dense"

    def __init__(
        self, store: ChunkStore, encoder: Encoder, index: faiss.Index, chunk_ids: list[str]
    ) -> None:
        self.store = store
        self.encoder = encoder
        self.index = index
        self.chunk_ids = chunk_ids

    @classmethod
    def build(cls, store: ChunkStore, encoder: Encoder, batch_size: int = 32) -> DenseRetriever:
        """Embed every chunk with the ``passage: `` prefix and build the index."""
        if not len(store):
            raise ValueError("cannot build a dense index over zero chunks")
        chunk_ids = [c["chunk_id"] for c in store.chunks]
        vectors = embed(encoder, [PASSAGE_PREFIX + c["text"] for c in store.chunks], batch_size)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        return cls(store, encoder, index, chunk_ids)

    def search(self, query: str, k: int) -> list[Hit]:
        """Top-``k`` chunks by cosine similarity to the ``query: ``-prefixed question."""
        if k <= 0 or not query.strip():
            return []
        vector = embed(self.encoder, [QUERY_PREFIX + query])
        scores, rows = self.index.search(vector, min(k, self.index.ntotal))
        return [
            self.store.hit(self.chunk_ids[row], score)
            for score, row in zip(scores[0], rows[0], strict=True)
            if row >= 0
        ]

    def save(self, index_dir: Path, model_name: str = "") -> None:
        """Write ``dense.faiss`` and the row -> chunk_id mapping ``dense_ids.json``."""
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_dir / FAISS_FILE))
        meta = {"model": model_name, "dim": self.index.d, "chunk_ids": self.chunk_ids}
        (index_dir / IDS_FILE).write_text(json.dumps(meta), encoding="utf-8")

    @classmethod
    def load(
        cls, index_dir: Path, store: ChunkStore, encoder: Encoder, model_name: str = ""
    ) -> DenseRetriever:
        """Load the FAISS index and id mapping written by :meth:`save`."""
        index = faiss.read_index(str(index_dir / FAISS_FILE))
        meta = json.loads((index_dir / IDS_FILE).read_text(encoding="utf-8"))
        chunk_ids = meta["chunk_ids"]
        if model_name and meta.get("model") and meta["model"] != model_name:
            raise StaleIndexError(
                f"dense index was built with {meta['model']}, not {model_name}; rebuild it"
            )
        if index.ntotal != len(chunk_ids) or any(cid not in store for cid in chunk_ids):
            raise StaleIndexError("dense index does not match chunks.jsonl; rebuild the index")
        if len(chunk_ids) != len(store):
            raise StaleIndexError("dense index does not match chunks.jsonl; rebuild the index")
        return cls(store, encoder, index, chunk_ids)
