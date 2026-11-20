"""Run the acceptance questions through the chatbot and score what can be scored automatically.

Usage:
    python eval/run_eval.py                       # full answers (calls the LLM)
    python eval/run_eval.py --retrieval-only      # retrieval metrics only, no LLM calls
    python eval/run_eval.py --questions path/to/evaluation_questions.json --mode hybrid

Automatic checks per question (expected sources = ``expected_source_ids``):
- retrieval_hit: at least one expected source among the top-k retrieved chunks;
- retrieval_all: every expected source retrieved; first_rank: rank of the first one;
- citation_hit / citation_precision: cited documents vs. expected sources;
- response_type (answer / clarify / not_found / refused / smalltalk).
Whether each claim is supported and whether clarification was appropriate needs a human
reading the answer against ``expected_behavior``; the report lists both side by side.
Writes eval/results/<run>.jsonl (all details) and <run>.md (summary table).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def load_questions(path: Path) -> list[dict[str, Any]]:
    """Read the questions list from an evaluation_questions.json file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data["questions"] if isinstance(data, dict) else data
    for q in questions:
        if not {"id", "question", "expected_source_ids"} <= set(q):
            raise ValueError(f"{path}: question without id/question/expected_source_ids: {q}")
    return questions


def score(expected: list[str], retrieved: list[str], cited: list[str]) -> dict[str, Any]:
    """Automatic retrieval and citation metrics for one question (doc-level)."""
    expected_set = set(expected)
    ranks = [i for i, doc in enumerate(retrieved, 1) if doc in expected_set]
    cited_set = set(cited)
    return {
        "retrieval_hit": bool(ranks) if expected else None,
        "retrieval_all": expected_set <= set(retrieved) if expected else None,
        "first_rank": ranks[0] if ranks else None,
        "citation_hit": bool(cited_set & expected_set) if expected and cited else None,
        "citation_precision": (
            round(len(cited_set & expected_set) / len(cited_set), 2)
            if expected and cited_set
            else None
        ),
    }


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Answer (or only retrieve for) every question; return one record per question."""
    from app.generation.pipeline import AnswerPipeline

    pipeline = AnswerPipeline.from_settings(args.mode)
    records = []
    for q in load_questions(args.questions):
        start = time.perf_counter()
        if args.retrieval_only:
            hits, timings = pipeline.retrieve(q["question"])
            retrieved = [h.doc_id for h in hits]
            record = {"retrieved_chunks": [h.chunk_id for h in hits], "timings_ms": timings}
            record["best_score"] = round(hits[0].score, 4) if hits else None
            cited: list[str] = []
        else:
            result = pipeline.answer(q["question"])
            retrieved = [r["doc_id"] for r in result.retrieved]
            cited = _dedupe([c.doc_id for c in result.citations])
            record = {
                "response_type": result.response_type,
                "retried": result.retried,
                "refused": result.refused,
                "refusal_reason": result.refusal_reason,
                "best_score": result.best_score,
                "answer": result.answer,
                "cited_numbers": [c.number for c in result.citations],
                "retrieved_chunks": [r["chunk_id"] for r in result.retrieved],
                "timings_ms": result.timings_ms,
            }
        record = {
            "id": q["id"],
            "question": q["question"],
            "expected_source_ids": q["expected_source_ids"],
            "expected_behavior": q.get("expected_behavior", ""),
            "retrieved_doc_ids": _dedupe(retrieved),
            "cited_doc_ids": cited,
            **score(q["expected_source_ids"], retrieved, cited),
            **record,
            "seconds": round(time.perf_counter() - start, 1),
        }
        records.append(record)
        print(
            f"{q['id']}  hit={record['retrieval_hit']!s:5} cited={','.join(cited) or '-':12} "
            f"type={record.get('response_type', '-'):9} {record['seconds']:5.1f}s  {q['question']}",
            flush=True,
        )
    return records


def _rate(values: list[bool | None]) -> str:
    scored = [v for v in values if v is not None]
    return f"{sum(scored)}/{len(scored)}" if scored else "-"


def summary(records: list[dict[str, Any]], args: argparse.Namespace) -> str:
    """Markdown report: aggregate metrics and a per-question table."""
    settings = get_settings()
    precisions = [r["citation_precision"] for r in records if r["citation_precision"] is not None]
    types: dict[str, int] = {}
    for r in records:
        types[r.get("response_type", "-")] = types.get(r.get("response_type", "-"), 0) + 1
    lines = [
        f"# Evaluation run {args.run_name}",
        "",
        f"- Questions: {len(records)} from `{args.questions.name}`; mode `{args.mode}`"
        f"{' (retrieval only)' if args.retrieval_only else ''}",
        f"- Settings: top_k_final={settings.top_k_final}, rerank_candidates="
        f"{settings.rerank_candidates}, rerank_max_length={settings.rerank_max_length}, "
        f"refusal_threshold={settings.refusal_threshold}, chunk_tokens={settings.chunk_tokens}, "
        f"llm={settings.llm_model}",
        f"- Retrieval: expected source in top {settings.top_k_final}: "
        f"{_rate([r['retrieval_hit'] for r in records])}; all expected sources: "
        f"{_rate([r['retrieval_all'] for r in records])}",
    ]
    if not args.retrieval_only:
        lines += [
            f"- Citations: cites an expected source: "
            f"{_rate([r['citation_hit'] for r in records])}; mean citation precision: "
            f"{statistics.mean(precisions):.2f}"
            if precisions
            else "- Citations: none",
            f"- Response types: {', '.join(f'{k} {v}' for k, v in sorted(types.items()))}",
            f"- Median time per question: {statistics.median(r['seconds'] for r in records):.1f} s",
        ]
    lines += [
        "",
        "| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        best = "-" if r.get("best_score") is None else f"{r['best_score']:.3f}"
        lines.append(
            f"| {r['id']} | {', '.join(r['expected_source_ids']) or '-'} | "
            f"{', '.join(r['retrieved_doc_ids']) or '-'} | {', '.join(r['cited_doc_ids']) or '-'} "
            f"| {r.get('response_type', '-')} | {r['retrieval_hit']} | {best} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--questions", type=Path, default=settings.collection_dir / "evaluation_questions.json"
    )
    parser.add_argument("--mode", default="hybrid_rerank")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "eval" / "results")
    parser.add_argument("--name", default=None, help="run name (default: timestamp)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    kind = "retrieval" if args.retrieval_only else "full"
    args.run_name = args.name or f"{datetime.now():%Y%m%d-%H%M%S}-{kind}"

    records = run(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = args.out_dir / f"{args.run_name}.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = summary(records, args)
    (args.out_dir / f"{args.run_name}.md").write_text(report, encoding="utf-8")
    print("\n" + report.split("\n| ID")[0])
    print(f"Wrote {jsonl} and {jsonl.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
