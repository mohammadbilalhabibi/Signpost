# Held-out retrieval: all four modes

25 questions from `eval/heldout_questions.json` (20 with expected sources: 15 single, 5 multi;
5 unanswerable), retrieval only, no LLM calls, 21 November 2026. Code and settings unchanged
(top_k_final=5, rerank_candidates=20, rerank_max_length=256, max 3 chunks per document).

| Mode | Hit@5 | Top-1 | MRR@10 |
|---|---|---|---|
| `bm25` | 15/20 | 15/20 | 0.768 |
| `dense` | 17/20 | 16/20 | 0.845 |
| `hybrid` | 20/20 | 14/20 | 0.804 |
| `hybrid_rerank` | 20/20 | 16/20 | 0.887 |

- **Hit@5**: an expected source among the 5 passages the LLM would get (from
  `heldout-retrieval-<mode>.md`, written by `eval/run_eval.py --retrieval-only`).
- **Top-1**: the first passage comes from an expected source.
- **MRR@10**: mean of 1 / rank of the first passage from an expected source within the top
  10 (0 if none), over the 20 answerable questions.

Top-1 and MRR@10 come from `heldout-retrieval-mrr10.json`. It was made with a one-off script
(not in the repository) that calls the pipeline's own `retrieve()` with `top_k_final=10`
for this measurement only; its Hit@5 matches `run_eval.py` for every mode. The JSON also
lists every question's top-10 documents and best score.

Best reranker score of the unanswerable questions (`hybrid_rerank`, refusal threshold 0.02):
H21 0.0022, H22 0.0233, H23 0.0297, H24 0.0340, H25 0.0052. The lowest answerable ones:
H12 0.0360, H10 0.0373, H06 0.0394.
