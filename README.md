# Degbot 2.0

A bilingual (German/English) question-answering assistant for international
students at Deggendorf Institute of Technology (DIT) and in Bavaria: enrolment,
Anmeldung, housing, health insurance, banking, exams. Every answer cites its
sources; if the answer is not in the sources, Degbot says so.

> Status: ingestion, chunking, retrieval (BM25, dense, hybrid, reranked) and answer
> generation with citations are implemented. The API endpoint and evaluation are not
> implemented yet.

## Stack

FastAPI · multilingual-e5-base embeddings · BM25 + FAISS hybrid retrieval with
Reciprocal Rank Fusion · bge-reranker-v2-m3 · any OpenAI-compatible LLM.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env             # then fill in LLM_API_KEY etc.
pip install -e ".[export]"       # once, for the reranker export below
python scripts/export_reranker.py
```

## Common tasks

With `make` (Linux/macOS/WSL):

| Command        | What it does                          |
|----------------|---------------------------------------|
| `make install` | Install the package + dev tools       |
| `make ingest`  | Download, clean and chunk sources     |
| `make index`   | Build FAISS + BM25 indexes            |
| `make reranker`| Export the int8 ONNX reranker (once)  |
| `make serve`   | Run the API on http://localhost:7860  |
| `make eval`    | Run the evaluation (stub)             |
| `make test`    | Run pytest                            |
| `make lint`    | Run ruff check + format check         |
| `make format`  | Auto-format and auto-fix with ruff    |

Without `make` (e.g. Windows), run the underlying commands directly:

```bash
ruff check .
pytest
uvicorn app.api:app --reload --port 7860
```

## Ingestion

Sources are listed in [data/sources.yaml](data/sources.yaml) (`url`, `type: html|pdf`,
optional `title`). Then run:

```bash
python scripts/ingest.py             # reuses files already downloaded to data/raw/
python scripts/ingest.py --refresh   # re-download everything
python scripts/ingest.py --rechunk   # only re-chunk documents.jsonl (no downloads)
```

What it does:

1. **Download politely** – checks `robots.txt`, waits at least 1 s between requests to
   the same host (longer if `Crawl-delay` says so), sends `INGEST_USER_AGENT`. Failed
   URLs are logged and skipped; bot-protection/challenge pages are detected and
   reported as failed (never bypassed). Raw files + a `.meta.json` go to `data/raw/`.
2. **Extract text** – trafilatura for HTML (main content only, headings kept as `#`),
   PyMuPDF for PDFs (larger fonts and short bold lines such as `§ 4 Prüfungskommission`
   become headings, wrapped lines are re-joined, table cells joined with `|`, running
   headers/footers, page numbers, TOC lines and superscript numbers dropped). Cookie banners and lines repeated
   across pages of the same site are removed.
3. **Detect language** (`de`/`en`, langdetect) and write
   `data/processed/documents.jsonl` (`doc_id, title, url, language, fetched_at, text`).
4. **Chunk** ([app/ingest/chunker.py](app/ingest/chunker.py)) – split at headings, merge
   small neighbouring sections under the same parent heading (below
   `CHUNK_MIN_SECTION_TOKENS`, default a quarter of the chunk size), then
   pack whole sentences into chunks of at most `CHUNK_TOKENS` (default 350, counted with
   the multilingual-e5 tokenizer, prefix included) with `CHUNK_OVERLAP` (default 15 %)
   overlap. Each chunk starts with `"<title> > <section>"`. Written to
   `data/processed/chunks.jsonl` (`chunk_id, doc_id, title, url, language, section,
   text, n_tokens`).
5. Prints a summary: documents per language, number of chunks, average chunk length,
   failed URLs.

## Retrieval

```bash
python scripts/build_index.py                                      # = make index
python scripts/export_reranker.py                                  # once, = make reranker
python scripts/search.py "Wie hoch ist der Semesterbeitrag?" --mode hybrid_rerank
python scripts/search.py "Can I work as a student?" --mode all --k 3
```

All retrievers implement `Retriever.search(query, k) -> list[Hit]`
([app/retrieval/base.py](app/retrieval/base.py)); `get_retriever(mode)` in
[app/retrieval/factory.py](app/retrieval/factory.py) creates them and loads every model
once per process.

| Mode            | What it does                                                          | Score            |
|-----------------|-----------------------------------------------------------------------|------------------|
| `bm25`          | rank_bm25; lowercase, letters + digits (umlauts, ß kept), DE+EN stopwords | BM25             |
| `dense`         | multilingual-e5-base (`passage: ` / `query: `), normalised, FAISS IndexFlatIP | cosine           |
| `hybrid`        | top `TOP_K_RETRIEVE` (20) of dense and BM25, Reciprocal Rank Fusion (`RRF_K`=60) | RRF              |
| `hybrid_rerank` | hybrid's top `TOP_K_RERANK` (10) reranked by bge-reranker-v2-m3; returns `k` results | reranker, 0–1    |

`index/` holds `bm25.pkl`, `dense.faiss`, `dense_ids.json` (row -> chunk_id) and
`meta.json` (a fingerprint of chunks.jsonl). If the chunks change, loading fails with a
"rebuild the index" error. The first build/search downloads the models from Hugging Face
(~1.1 GB e5 + ~2.3 GB reranker).

### Reranker backend and latency

Reranking is ~99% of the query time on CPU. By default (`RERANKER_BACKEND=onnx`) the
reranker runs as an int8 ONNX export with ONNX Runtime
([app/retrieval/onnx_reranker.py](app/retrieval/onnx_reranker.py)). Create the export once
with `python scripts/export_reranker.py` (needs `pip install -e ".[export]"`, a few minutes;
writes ~570 MB to `models/`, git-ignored). `RERANKER_BACKEND=torch` uses the original fp32
model instead and needs no export.

Measured on an i7-1165G7 laptop (4 cores, CPU only), models loaded once, 10 queries,
`hybrid_rerank`, k=5:

| Reranker setup                              | Median per query | Slowest |
|---------------------------------------------|------------------|---------|
| fp32 PyTorch, 20 candidates (previous)      | 24.6 s           | 31.0 s  |
| int8 ONNX, 10 candidates (default)          | 7.2–8.8 s        | 8.0–11.6 s |

The int8 range covers several runs on different occasions: the same model and code
varied by about 20% with the machine's state. The 8 s goal is therefore met only some of
the time.

On 100 query–chunk pairs the int8 scores differ from fp32 by 0.015 on average (max 0.11),
and both picked the same best chunk for all 10 questions. Cutting to 10 candidates changes
more: the top result matched the previous setup in 7 of 10 queries. Whether that costs
answer quality is still to be measured on the evaluation set. Model load takes ~25 s at
startup. A smaller cloud CPU (e.g. a free Hugging Face Space) will be slower.

Tests: `pytest` runs fast tests with small fake models; `pytest -m slow` also runs the
same corpus through the real e5 and reranker models and checks the int8 ONNX export
against the PyTorch reranker.

## Answering

```bash
python scripts/ask.py "How do I register my address in Deggendorf?"
python scripts/ask.py "Wie hoch ist der Semesterbeitrag?" "Can I work as a student?"
python scripts/ask.py --interactive            # models load once, then ask many questions
```

`AnswerPipeline` ([app/generation/pipeline.py](app/generation/pipeline.py)) is built once
(retriever models + LLM client) and answers each question:

1. retrieves the top `TOP_K_FINAL` (5) chunks (`hybrid_rerank` by default, `--mode` to change);
2. if the best reranker score is below `REFUSAL_THRESHOLD`, returns a fixed "I couldn't find
   this in my sources" answer in the question's language **without calling the LLM**;
3. otherwise sends the numbered passages to the LLM with the rules in
   [app/generation/prompts.py](app/generation/prompts.py): answer only from the passages, in
   the question's language, cite `[1]`, `[2]` after each claim, say so and name an office if
   the answer is missing, at most 5 sentences;
4. returns the answer, the citations actually used (number, title, url, snippet),
   `refused`, the mode and timings in ms (retrieval, reranking, generation, total).

An answer that cites no passage is also marked `refused` (`refusal_reason: no_citations`).
The threshold applies only to `hybrid_rerank`; other modes have no 0–1 score.

The LLM client ([app/generation/llm_client.py](app/generation/llm_client.py)) works with
any OpenAI-compatible API; set `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`
(examples for OpenAI, Azure OpenAI, Mistral and Ollama in [.env.example](.env.example)).
Requests time out after `LLM_TIMEOUT` seconds and are retried once. Newer OpenAI models
reject `max_tokens`, so `LLM_TOKEN_PARAM=auto` sends `max_completion_tokens` for
openai/azure and `max_tokens` elsewhere.

## Layout

```
app/            api.py, config.py, ingest/, retrieval/, generation/, static/
data/raw/       downloaded source files (git-ignored)
data/processed/ cleaned documents and chunks (JSONL)
index/          FAISS + BM25 artifacts (git-ignored)
models/         exported int8 ONNX reranker (git-ignored)
eval/           questions, evaluation runner, results
scripts/        CLI scripts
tests/          pytest tests
```

## Configuration

All settings are read from environment variables / `.env`; see
[.env.example](.env.example) for the full list.
