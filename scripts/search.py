"""Search the index from the command line.

Usage:
    python scripts/search.py "Wie hoch ist der Semesterbeitrag?" --mode hybrid_rerank
    python scripts/search.py "Can I work as a student?" --mode all --k 3
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from app.config import get_settings
from app.retrieval.base import Hit
from app.retrieval.factory import MODES, get_retriever


def format_hits(hits: list[Hit], preview_chars: int = 150) -> str:
    """Render hits as numbered lines: rank, score, title and a text preview."""
    lines = []
    for rank, hit in enumerate(hits, start=1):
        body = hit.text.split("\n\n", 1)[-1]  # drop the "title > section" prefix
        preview = " ".join(body.split())[:preview_chars]
        lines.append(f"{rank:>2}. [{hit.score:.4f}] {hit.title}  ({hit.language})")
        lines.append(f"    {hit.chunk_id}")
        lines.append(f"    {preview}…")
    return "\n".join(lines) if lines else "    (no results)"


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("question")
    parser.add_argument("--mode", choices=[*MODES, "all"], default="hybrid_rerank")
    parser.add_argument("--k", type=int, default=get_settings().top_k_final)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # umlauts on Windows consoles

    for mode in MODES if args.mode == "all" else [args.mode]:
        retriever = get_retriever(mode)
        start = time.perf_counter()
        hits = retriever.search(args.question, args.k)
        elapsed = time.perf_counter() - start
        print(f"\n=== {mode}  ({elapsed:.2f} s) — {args.question}")
        print(format_hits(hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
