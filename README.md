# Degbot 2.0

A bilingual (German/English) question-answering assistant for international
students at Deggendorf Institute of Technology (DIT) and in Bavaria: enrolment,
Anmeldung, housing, health insurance, banking, exams. Every answer cites its
sources; if the answer is not in the sources, Degbot says so.

> Status: ingestion and chunking are implemented. Retrieval, generation and
> evaluation are not implemented yet.

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
```

## Common tasks

With `make` (Linux/macOS/WSL):

| Command        | What it does                          |
|----------------|---------------------------------------|
| `make install` | Install the package + dev tools       |
| `make ingest`  | Download, clean and chunk sources     |
| `make index`   | Build FAISS + BM25 indexes (stub)     |
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

## Layout

```
app/            api.py, config.py, ingest/, retrieval/, generation/, static/
data/raw/       downloaded source files (git-ignored)
data/processed/ cleaned documents and chunks (JSONL)
index/          FAISS + BM25 artifacts (git-ignored)
eval/           questions, evaluation runner, results
scripts/        CLI scripts
tests/          pytest tests
```

## Configuration

All settings are read from environment variables / `.env`; see
[.env.example](.env.example) for the full list.
