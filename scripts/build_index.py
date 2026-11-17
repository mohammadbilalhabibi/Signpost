"""Build the BM25 and FAISS indexes from data/processed/chunks.jsonl into index/.

Usage:
    python scripts/build_index.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.retrieval.base import ChunkStore
from app.retrieval.factory import build_indexes, load_embedding_model


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--chunks", type=Path, default=settings.chunks_path)
    parser.add_argument("--index-dir", type=Path, default=settings.index_dir)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
    )
    for noisy in ("httpx", "httpx2", "httpcore", "huggingface_hub", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    store = ChunkStore.from_jsonl(args.chunks)
    print(f"Loaded {len(store)} chunks from {args.chunks}")
    encoder = load_embedding_model(settings.embedding_model)
    meta = build_indexes(store, args.index_dir, encoder, settings.embedding_model)

    print()
    print("=== Index summary ===")
    print(f"Chunks:          {meta['chunks']}")
    print(f"BM25:            {args.index_dir / 'bm25.pkl'} ({meta['seconds']['bm25']} s)")
    print(
        f"Dense (FAISS):   {args.index_dir / 'dense.faiss'} "
        f"(dim {meta['embedding_dim']}, {meta['seconds']['dense']} s)"
    )
    print(f"Embedding model: {meta['embedding_model']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
