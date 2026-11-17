"""Build/load indexes and create retrievers by mode, loading each model only once."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal, get_args

from app.config import Settings, get_settings
from app.retrieval.base import ChunkStore, Retriever, StaleIndexError
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever, Encoder
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.onnx_reranker import OnnxCrossEncoder
from app.retrieval.rerank import CrossEncoderLike, RerankedRetriever

logger = logging.getLogger(__name__)

Mode = Literal["bm25", "dense", "hybrid", "hybrid_rerank"]
MODES: tuple[str, ...] = get_args(Mode)
META_FILE = "meta.json"


# ------------------------------------------------------------------ model loading


@lru_cache(maxsize=2)
def load_embedding_model(model_name: str) -> Encoder:
    """Load the sentence-transformers embedding model (once per process)."""
    from sentence_transformers import SentenceTransformer

    logger.info("loading embedding model %s", model_name)
    return SentenceTransformer(model_name)


@lru_cache(maxsize=2)
def load_reranker(model_name: str) -> CrossEncoderLike:
    """Load the cross-encoder reranker (once per process)."""
    from sentence_transformers import CrossEncoder

    logger.info("loading reranker %s", model_name)
    return CrossEncoder(model_name, max_length=512)


@lru_cache(maxsize=2)
def load_onnx_reranker(
    model_dir: Path, source_model: str | None = None, threads: int = 0
) -> OnnxCrossEncoder:
    """Load the int8 ONNX reranker exported by scripts/export_reranker.py (once per process)."""
    return OnnxCrossEncoder.from_dir(model_dir, expected_model=source_model, threads=threads)


def reranker_from_settings(settings: Settings) -> CrossEncoderLike:
    """Return the reranker selected by RERANKER_BACKEND (onnx or torch)."""
    if settings.reranker_backend == "onnx":
        return load_onnx_reranker(
            Path(settings.reranker_onnx_dir), settings.reranker_model, settings.reranker_threads
        )
    return load_reranker(settings.reranker_model)


# ------------------------------------------------------------------ index building


def build_indexes(store: ChunkStore, index_dir: Path, encoder: Encoder, model_name: str) -> dict:
    """Build BM25 and dense indexes for ``store``, save them and ``meta.json``.

    Returns the metadata written (counts, timings, fingerprint).
    """
    t0 = time.perf_counter()
    BM25Retriever.build(store).save(index_dir)
    t_bm25 = time.perf_counter() - t0

    t0 = time.perf_counter()
    dense = DenseRetriever.build(store, encoder)
    dense.save(index_dir, model_name=model_name)
    t_dense = time.perf_counter() - t0

    meta = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "chunks": len(store),
        "fingerprint": store.fingerprint(),
        "embedding_model": model_name,
        "embedding_dim": dense.index.d,
        "seconds": {"bm25": round(t_bm25, 2), "dense": round(t_dense, 2)},
    }
    (index_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def check_index(index_dir: Path, store: ChunkStore) -> dict:
    """Raise StaleIndexError unless ``index_dir`` was built from exactly these chunks."""
    meta_path = index_dir / META_FILE
    if not meta_path.exists():
        raise StaleIndexError(f"no index in {index_dir}; run scripts/build_index.py")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("fingerprint") != store.fingerprint():
        raise StaleIndexError(
            "chunks.jsonl changed since the index was built; run scripts/build_index.py"
        )
    return meta


# ---------------------------------------------------------------------- factory


@lru_cache(maxsize=4)
def _load_store(chunks_path: Path) -> ChunkStore:
    return ChunkStore.from_jsonl(chunks_path)


@lru_cache(maxsize=8)
def _cached_retriever(mode: str) -> Retriever:
    return _make_retriever(mode, get_settings())


def get_retriever(mode: Mode, settings: Settings | None = None) -> Retriever:
    """Return the retriever for ``mode`` (bm25, dense, hybrid, hybrid_rerank).

    Indexes, chunks and models are loaded once and shared between modes; with the
    default settings the retriever object itself is cached as well.
    """
    if mode not in MODES:
        raise ValueError(f"unknown retrieval mode {mode!r}; choose one of {', '.join(MODES)}")
    if settings is None:
        return _cached_retriever(mode)
    return _make_retriever(mode, settings)


def _make_retriever(mode: str, settings: Settings) -> Retriever:
    index_dir = Path(settings.index_dir)
    store = _load_store(Path(settings.chunks_path))
    check_index(index_dir, store)

    def bm25() -> BM25Retriever:
        return BM25Retriever.load(index_dir, store)

    def dense() -> DenseRetriever:
        encoder = load_embedding_model(settings.embedding_model)
        return DenseRetriever.load(index_dir, store, encoder, settings.embedding_model)

    if mode == "bm25":
        return bm25()
    if mode == "dense":
        return dense()
    hybrid = HybridRetriever(
        [dense(), bm25()], candidates=settings.top_k_retrieve, rrf_k=settings.rrf_k
    )
    if mode == "hybrid":
        return hybrid
    return RerankedRetriever(
        hybrid, reranker_from_settings(settings), candidates=settings.top_k_rerank
    )
