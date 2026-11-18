"""Ask Degbot questions from the command line.

Models and the LLM client are loaded once, then every question reuses them.

Usage:
    python scripts/ask.py "How do I register my address in Deggendorf?"
    python scripts/ask.py "Question one?" "Frage zwei?" --mode hybrid_rerank
    python scripts/ask.py --interactive
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from app.generation.llm_client import GenerationError
from app.generation.pipeline import Answer, AnswerPipeline
from app.retrieval.factory import MODES


def format_answer(result: Answer) -> str:
    """Human-readable answer with citations, refusal flag, best score and timings."""
    lines = [result.answer, ""]
    if result.citations:
        lines.append("Sources:")
        for c in result.citations:
            lines += [f"  [{c.number}] {c.title} – {c.url}", f"      {c.snippet}"]
    else:
        lines.append("Sources: none")
    best = "-" if result.best_score is None else f"{result.best_score:.3f}"
    timings = ", ".join(
        f"{name} {'-' if ms is None else f'{ms:.0f}'}" for name, ms in result.timings_ms.items()
    )
    reason = f" ({result.refusal_reason})" if result.refused else ""
    lines += [
        "",
        f"refused: {result.refused}{reason} | language: {result.language} | "
        f"mode: {result.mode} | best score: {best}",
        f"timings ms: {timings}",
    ]
    return "\n".join(lines)


def ask(pipeline: AnswerPipeline, question: str) -> None:
    """Answer one question and print it; LLM errors are printed, not raised."""
    print(f"\n=== {question}")
    try:
        print(format_answer(pipeline.answer(question)))
    except GenerationError as exc:
        print(f"ERROR: {exc}")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("questions", nargs="*", help="one or more questions")
    parser.add_argument("--mode", choices=MODES, default="hybrid_rerank")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="keep asking (empty line or exit quits)"
    )
    args = parser.parse_args(argv)
    if not args.questions and not args.interactive:
        parser.error("give a question or use --interactive")

    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    start = time.perf_counter()
    pipeline = AnswerPipeline.from_settings(args.mode)
    print(f"loaded {args.mode} pipeline in {time.perf_counter() - start:.1f} s")

    for question in args.questions:
        ask(pipeline, question)
    if args.interactive:
        while True:
            try:
                question = input("\nQuestion (empty line to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question or question.lower() in {"exit", "quit"}:
                break
            ask(pipeline, question)
    return 0


if __name__ == "__main__":
    sys.exit(main())
