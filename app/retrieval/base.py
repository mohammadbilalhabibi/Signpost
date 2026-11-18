"""Common retrieval types: the Hit result, the Retriever interface and the chunk store."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ingest.jsonl import read_jsonl


@dataclass(frozen=True)
class Hit:
    """One retrieved chunk with its score (meaning depends on the retriever)."""

    chunk_id: str
    doc_id: str
    score: float
    text: str
    title: str
    url: str
    language: str
    # source metadata from ingestion (publisher, edition/period, dates, notes, ...)
    meta: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)


class Retriever(ABC):
    """Interface shared by all retrievers, so evaluation can swap them freely."""

    name: str = "retriever"

    @abstractmethod
    def search(self, query: str, k: int) -> list[Hit]:
        """Return up to ``k`` hits for ``query``, best first."""


class ChunkStore:
    """All chunks in memory, addressable by chunk_id (loaded once)."""

    def __init__(self, chunks: Iterable[dict]) -> None:
        self.chunks: list[dict] = list(chunks)
        self._by_id = {c["chunk_id"]: c for c in self.chunks}
        if len(self._by_id) != len(self.chunks):
            raise ValueError("duplicate chunk_id in chunk store")

    @classmethod
    def from_jsonl(cls, path: Path) -> ChunkStore:
        """Load chunks from a chunks.jsonl file."""
        if not path.exists():
            raise FileNotFoundError(f"{path} not found; run scripts/ingest.py first")
        return cls(read_jsonl(path))

    def __len__(self) -> int:
        return len(self.chunks)

    def __contains__(self, chunk_id: object) -> bool:
        return chunk_id in self._by_id

    def get(self, chunk_id: str) -> dict:
        """Return the chunk record for ``chunk_id``."""
        return self._by_id[chunk_id]

    def hit(self, chunk_id: str, score: float) -> Hit:
        """Build a Hit for ``chunk_id`` with the given score."""
        c = self._by_id[chunk_id]
        return Hit(
            chunk_id=chunk_id,
            doc_id=c["doc_id"],
            score=float(score),
            text=c["text"],
            title=c.get("title", ""),
            url=c.get("url", ""),
            language=c.get("language", "unknown"),
            meta=c.get("meta") or {},
        )

    def fingerprint(self) -> str:
        """Hash over chunk ids and texts; used to detect a stale index."""
        digest = hashlib.sha256()
        for c in self.chunks:
            digest.update(c["chunk_id"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(c["text"].encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()


class StaleIndexError(RuntimeError):
    """The saved index does not match the current chunks; rebuild it."""
