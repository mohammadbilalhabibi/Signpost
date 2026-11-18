"""Build data/processed/{documents,chunks}.jsonl from the source collection.

Usage:
    python scripts/ingest.py               # the curated collection in COLLECTION_DIR
    python scripts/ingest.py --rechunk     # only re-chunk data/processed/documents.jsonl
    python scripts/ingest.py --urls my_sources.yaml [--refresh]
                                           # optional: crawl a YAML list of URLs instead
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.ingest.chunker import Chunker, hf_token_counter
from app.ingest.collection import ingest_collection
from app.ingest.fetcher import PoliteFetcher
from app.ingest.pipeline import rechunk, run_ingest
from app.ingest.sources import load_sources

ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--collection", type=Path, default=None, help="collection folder (default COLLECTION_DIR)"
    )
    parser.add_argument(
        "--urls", type=Path, default=None, help="crawl this sources.yaml instead of the collection"
    )
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--refresh", action="store_true", help="with --urls: re-download")
    parser.add_argument(
        "--rechunk", action="store_true", help="re-chunk existing documents, no downloads"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a non-zero exit code only if nothing could be ingested."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "httpx2", "httpcore", "trafilatura", "urllib3", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = get_settings()
    chunker = Chunker(
        count_tokens=hf_token_counter(settings.embedding_model),
        chunk_tokens=settings.chunk_tokens,
        overlap=settings.chunk_overlap,
        min_section_tokens=settings.chunk_min_section_tokens,
    )
    if args.rechunk:
        report = rechunk(args.out_dir, chunker)
        print()
        print(report.summary())
        print(f"\nWrote {args.out_dir / 'chunks.jsonl'}")
        return 0

    if args.urls:
        sources = load_sources(args.urls)
        with PoliteFetcher(
            user_agent=settings.ingest_user_agent,
            delay=settings.ingest_request_delay,
            timeout=settings.ingest_timeout,
        ) as fetcher:
            report = run_ingest(sources, args.raw_dir, args.out_dir, fetcher, chunker, args.refresh)
    else:
        collection = args.collection or settings.collection_dir
        print(f"Ingesting collection {collection}")
        report = ingest_collection(collection, args.out_dir, chunker)

    print()
    print(report.summary())
    for doc in report.documents:
        print(f"  {doc['doc_id']}  {doc.get('representation', 'web'):4}  {doc['title']}")
    print(f"\nWrote {args.out_dir / 'documents.jsonl'} and {args.out_dir / 'chunks.jsonl'}")
    return 0 if report.documents else 1


if __name__ == "__main__":
    sys.exit(main())
