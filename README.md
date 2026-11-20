# Signpost

[![CI](https://github.com/mohammadbilalhabibi/Signpost/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammadbilalhabibi/Signpost/actions/workflows/ci.yml)
[![Docker](https://github.com/mohammadbilalhabibi/Signpost/actions/workflows/docker.yml/badge.svg)](https://github.com/mohammadbilalhabibi/Signpost/actions/workflows/docker.yml)

**A RAG assistant that answers international students' questions about arriving at
Deggendorf Institute of Technology (DIT), in English, with a citation to the official
source for every claim, and says so when the sources don't have the answer.**

**[Live demo](https://signpost.icyground-8b8d4d52.francecentral.azurecontainerapps.io)**:
the app scales to zero when idle, so the first visit after a quiet period takes about
15–20 s to wake up (measured 14 s and 20 s on Azure); after that, answers take about 9–12 s.

![Signpost answering a question with citations, highlighting a source, and declining an unanswerable question](docs/demo.gif)

<sub>Recorded on the live app. The "Searching the sources…" waits are sped up 4×; the real
times are shown under each answer.</sub>

Topics: enrolment, fees and re-registration, student ID and IT accounts, student housing,
address registration, residence permits, health insurance, banking and student jobs.
Signpost replaces my earlier rule-based chatbot "Degbot".

## Results

Measured on the 40 acceptance questions that come with the source collection
(38 have an expected source; the other two are a greeting and a live-vacancy question that
must be declined). Settings: `hybrid_rerank`, top 5 passages, `gpt-6-luna`.

| Run | Change | Expected source in top 5 | Cites an expected source | Citation precision | Review (pass / partial / fail) |
|---|---|---|---|---|---|
| run1 | new curated collection | 37/38 | 36/38 | 0.88 | 28 / 10 / 2 |
| run2 | source context in chunk headers; prompt: conditions, contacts | 38/38 | 38/38 | 0.93 | 31 / 8 / 1 |
| run3 | prompt: address registration vs residence permit kept apart | 38/38 | 38/38 | 0.91 | 31 / 9 / 0 |
| run4 | question outside the tagged passages; retry for uncited replies | 38/38 | 38/38 | 0.89 | 14 re-read: 8 / 6 / 0 |
| run5 | partial answers count as answers, not "not found" | 38/38 | 37/38 | 0.87 | not reviewed |

**Read these numbers with care.** These 40 questions are the only test set: the prompt
rules and the refusal threshold (0.02) were tuned on them, so they are a development
benchmark, not a held-out score. The review column is LLM-graded
(not by a human) against each question's rubric and the source texts. The LLM is not deterministic, so single grades can change between runs.

**Three findings**

1. **Dense retrieval finds the source; the reranker puts it first and knows when to say
   no.** Retrieval only, top 5 (`retrieval-*` runs): BM25 found an expected source for
   35/38 questions (top 1: 23/38), dense e5 for 38/38 (top 1: 29/38), hybrid RRF for 37/38
   (top 1: 29/38), and hybrid + reranker for 38/38 (top 1: 32/38). Hybrid alone did not beat
   dense here. Dense similarity scores can't separate an unanswerable question from a real
   one (0.79 for the live-vacancy question vs 0.82 for the lowest answerable one). The
   reranker can (0.0005 vs 0.03), which is what lets Signpost refuse before calling the LLM.
   The cost: reranking takes 7–9 s of the 9–12 s per answer on Azure.
2. **Better sources fixed answers more than tuning did.** The first version used 38 crawled
   URLs plus PDFs and documents of mixed quality, and its answers were unsatisfactory
   (judged by reading them; that version was never measured, so there is no before/after
   number). Switching to a curated collection of 30 English sources with publisher, period
   and URL metadata gave 36/38 answers citing an expected source in the first measured run;
   chunk-header and prompt changes then took that to 38/38 and removed the fails.
3. **"Not found" was hiding useful answers.** In 3 of the 5 earlier full runs, Q29 (is the
   rental contract the landlord confirmation?) came back as "not found" even though it
   cited the right source (D29), so the page showed a "No answer found" banner above useful
   content. Now a reply that cites passages is a partial answer that names what's missing
   and who to contact. In run5 no answer was "not found"; the only refusal was the
   live-vacancy question.

## Architecture

```mermaid
flowchart LR
    S["30 curated sources<br/>sources.json + text copies"] --> C["Chunking<br/>≤ 350 tokens, 191 chunks"]
    C --> B["BM25<br/>rank_bm25"]
    C --> D["FAISS<br/>multilingual-e5-base"]
    Q(["Student question"]) --> B & D
    B --> F["Reciprocal Rank Fusion<br/>k = 60, top 20"]
    D --> F
    F --> R["int8 ONNX reranker<br/>bge-reranker-v2-m3"]
    R --> T{"best score<br/>≥ 0.02?"}
    T -- no --> X["Fixed refusal<br/>no LLM call"]
    T -- yes --> L["LLM: top 5 passages<br/>answer with [n] citations"]
```

```mermaid
flowchart LR
    P["git push main"] --> CI["GitHub Actions: CI<br/>ruff + pytest"]
    P --> DK["GitHub Actions: Docker<br/>build, smoke test, memory check"]
    DK --> G["GHCR<br/>:latest and :commit"]
    G -- "scripts/deploy_azure.ps1" --> A["Azure Container Apps<br/>1.75 vCPU / 3.5 GiB, scale 0–1"]
```

## Design decisions and trade-offs

- **Curated sources, not a crawler**: fewer pages, but each has a publisher, period and
  original URL, so fees and deadlines stay attached to their semester.
- **Reranker as int8 ONNX**: about 9 s instead of 24.6 s (fp32) per query on a 4-core
  laptop, scores within 0.015 of fp32 on average. Its 0–1 score allows refusing below the
  threshold with a fixed message: no LLM call, nothing invented, but on-topic questions the
  sources can't answer get a generic refusal instead of a pointer to the right portal.
- **Grounding checks in code, not only in the prompt**: an uncited answer is asked once
  more; a "not found" that cites passages is shown as a partial answer.
- **Scale to zero, image from GHCR**: idle costs nothing and the free grant covers about
  28.6 running hours a month, at the price of a 15–20 s wake-up; Azure Container Registry
  would pull faster but costs about 5 USD/month.
- **Budget protection**: a per-IP rate limit that a spoofed `X-Forwarded-For` can't bypass,
  and at most 200 LLM-answered questions a day.

## Limitations

- Tested only on the 40 questions it was tuned on, and graded by an AI assistant.
- A snapshot from 18 November 2026: fees, deadlines and contacts need refreshing each
  semester; the official pages are authoritative. No live data (free rooms, appointments).
- Some answers miss a detail or a source (run5: Q13 cites one of its two expected sources,
  Q31 neither). CPU-only answers take about 9–12 s, mostly reranking.

## Run locally

Needs Docker and an API key for any OpenAI-compatible LLM. The image build downloads the
models and builds the index (several minutes, about 5.4 GB).

```bash
git clone https://github.com/mohammadbilalhabibi/Signpost.git && cd Signpost
cp .env.example .env     # then set LLM_API_KEY, LLM_BASE_URL and LLM_MODEL
docker build -t signpost .
docker run --rm -p 7860:7860 --env-file .env signpost    # open http://127.0.0.1:7860
```

Without Docker, see [Setup](#setup) below. Everything that follows is the detailed
technical documentation.

## Stack

FastAPI · multilingual-e5-base embeddings · BM25 + FAISS hybrid retrieval with
Reciprocal Rank Fusion · bge-reranker-v2-m3 · any OpenAI-compatible LLM.

## Setup

Requires Python 3.12+.

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
| `make ingest`  | Ingest and chunk the source collection |
| `make index`   | Build FAISS + BM25 indexes            |
| `make reranker`| Export the int8 ONNX reranker (once)  |
| `make serve`   | Run the API on http://localhost:7860  |
| `make eval`    | Run the 40 acceptance questions (LLM) |
| `make test`    | Run pytest                            |
| `make lint`    | Run ruff check + format check         |
| `make format`  | Auto-format and auto-fix with ruff    |

Without `make` (e.g. Windows), run the underlying commands directly:

```bash
ruff check .
pytest
python -m uvicorn app.api:app --port 7860
```

## Knowledge base and ingestion

The answer corpus is the curated collection in
[DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/](DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/)
(`COLLECTION_DIR`): 30 English sources about arriving at DIT and settling in Deggendorf
(DIT, Studierendenwerk Niederbayern/Oberpfalz, City and District of Deggendorf, Make it in
Germany, DAAD, ARD ZDF Deutschlandradio Beitragsservice, German federal law translation).
Its `sources.json` maps every source to its original URL, publisher, dates and
edition/semester; see the collection's own README for source precedence and coverage
limits.

```bash
python scripts/ingest.py             # collection -> data/processed/{documents,chunks}.jsonl
python scripts/ingest.py --rechunk   # only re-chunk documents.jsonl
python scripts/build_index.py        # then rebuild the BM25 + FAISS indexes
```

What [app/ingest/collection.py](app/ingest/collection.py) does:

1. Reads `sources.json` and uses **only `ingest: true`** sources, each **once**: the clean
   English text copy (`text_path`, Markdown with YAML front matter) or, if that is
   missing, the PDF (`pdf_path`, SHA-256 checked). `reference_only/`, `Source_Guide.pdf`,
   the README, `source_review.json` and
   `evaluation_questions.json` are never part of the corpus.
2. Keeps English content only (sources whose text is not English are rejected). D27 and
   D30 contain labelled English translations of German authority pages; they are cited
   with the original official URLs.
3. Moves Markdown link lines out of the indexed text into per-chunk link metadata (the
   URLs contained German words that added noise to keyword search), so the LLM still sees
   the form and portal links.
4. Chunks with [app/ingest/chunker.py](app/ingest/chunker.py): split at headings (FAQ
   questions and procedures stay together where they fit), merge small sibling sections,
   pack whole sentences into chunks of at most `CHUNK_TOKENS` (350) with 15 % overlap.
   Every chunk carries the source metadata (`meta`: source ID, publisher, source
   language, format, topic, geographic scope, access date, document date,
   edition/period, source note, links) and the original URL.

The older web crawler ([app/ingest/pipeline.py](app/ingest/pipeline.py): polite
fetching, robots.txt, trafilatura/PyMuPDF extraction) is still available for a YAML list
of URLs: `python scripts/ingest.py --urls my_sources.yaml`.

## Sources and attribution

The answer sources are public pages and documents of Deggendorf Institute of Technology,
Studierendenwerk Niederbayern/Oberpfalz, the City and the District (Landkreis) of
Deggendorf, Make it in Germany, DAAD, ARD ZDF Deutschlandradio Beitragsservice and the
official English translation of the Federal Registration Act (gesetze-im-internet.de).
The original publishers keep all rights to their content. Every answer links to the
original official page, and `sources.json` records each source's URL, publisher and
capture date. Only the English text copies needed by the pipeline are in this repository;
the publishers' PDFs (`documents/`, `reference_only/`, `Source_Guide.pdf`) are git-ignored
and not redistributed. D27 and D30 contain English translations or summaries of German
authority pages made for the collection; they are labelled as such, and the German
originals are authoritative. The collection is a snapshot of 18 November 2026: check the
original pages before relying on fees, deadlines or contacts.

## Retrieval

```bash
python scripts/build_index.py                                      # = make index
python scripts/export_reranker.py                                  # once, = make reranker
python scripts/search.py "How do I register my address?" --mode hybrid_rerank
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
| `hybrid_rerank` | hybrid's top `RERANK_CANDIDATES` (20, truncated to `RERANK_MAX_LENGTH`=256 tokens) reranked by bge-reranker-v2-m3; returns `k` results | reranker, 0–1    |

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
| int8 ONNX, 10 candidates, 512 tokens        | 7.2–8.8 s        | 8.0–11.6 s |

The int8 range covers several runs on different occasions: the same model and code
varied by about 20% with the machine's state. The 8 s goal is therefore met only some of
the time.

On 100 query–chunk pairs the int8 scores differ from fp32 by 0.015 on average (max 0.11),
and both picked the same best chunk for all 10 questions. Cutting to 10 candidates changes
more: the top result matched the previous setup in 7 of 10 queries. Whether that costs
answer quality is still to be measured on the evaluation set. Model load takes ~25 s at
startup. A smaller cloud CPU (e.g. a free Hugging Face Space) will be slower.

Two settings trade reranking speed against thoroughness: `RERANK_CANDIDATES` (default 20)
and `RERANK_MAX_LENGTH` (default 256 tokens per question + chunk pair; chunks are ≤ 350
tokens, so 512 never truncates, while 256 truncated 60 of 100 pairs). Reranking time only, int8 ONNX, 5 questions in one process:

| Candidates | Max length | Median reranking | Same top-1 as 20/512 | Top-5 overlap with 20/512 |
|------------|------------|------------------|----------------------|---------------------------|
| 20         | 512        | 16.2 s           | –                    | –                         |
| 20 (default) | 256 (default) | 9.1 s     | 5/5                  | 76%                       |
| 10         | 512        | 7.1 s            | 4/5                  | 60%                       |
| 10         | 256        | 4.3 s            | 3/5                  | 56%                       |

Tests: `pytest` runs fast tests with small fake models; `pytest -m slow` also runs the
same corpus through the real e5 and reranker models and checks the int8 ONNX export
against the PyTorch reranker.

## Answering

```bash
python scripts/ask.py "How do I register my address in Deggendorf?"
python scripts/ask.py "Which DIT fees do I pay?" "Can I work as a student?"
python scripts/ask.py --interactive            # models load once, then ask many questions
```

`AnswerPipeline` ([app/generation/pipeline.py](app/generation/pipeline.py)) is built once
(retriever models + LLM client) and answers each question:

1. greetings, thanks and goodbyes ("Hi! I am new here.") get a direct reply
   ([app/generation/smalltalk.py](app/generation/smalltalk.py)) without retrieval;
2. retrieves the top `TOP_K_FINAL` (5) chunks (`hybrid_rerank` by default, `--mode` to change);
3. if the best reranker score is below `REFUSAL_THRESHOLD`, returns a fixed "I couldn't find
   this in my sources" answer **without calling the LLM**;
4. otherwise sends today's date and the numbered passages, each with its source metadata
   (source ID, publisher, period/edition, document date, translation label, source note,
   links), to the LLM with the rules in [app/generation/prompts.py](app/generation/prompts.py):
   answer only from the passages and cite `[1]`, `[2]` after each claim; prefer the most
   specific source; keep fees and dates attached to their semester; flag conflicts and
   translated summaries; ask one short question when the answer depends on the semester,
   degree vs. exchange status, citizenship/residence status, campus or job type; never
   invent vacancies, appointments, premiums or legal decisions; answer in English unless
   the user explicitly asks for another language. The passages are wrapped in
   `<passages>` tags and the question is stated before and after them, so a passage that
   ends like an FAQ heading cannot swallow the question. A reply of type answer or clarify
   that cites nothing is sent once more with a correction (`retried` in the result);
5. returns the answer, `response_type` (`answer`, `clarify`, `not_found`, `refused`,
   `smalltalk`), the citations actually used (number, title, original url, snippet), the
   cited sources grouped per document, the retrieved chunks, `refused`, the mode and
   timings in ms (retrieval, reranking, generation, total).

`refused` is true for the score threshold and when the LLM reports that the passages contain
nothing useful for the question (`refusal_reason`: `low_score`, `no_hits`, `not_in_sources`).
If the passages answer part of a question, the reply gives that part, names the missing part
and who to contact, and counts as an `answer`; a `not_found` reply that cites passages is
treated as such a partial answer, so the page shows no "not found" banner above useful content.
The threshold applies only to `hybrid_rerank`; other modes have no 0–1 score.

The LLM client ([app/generation/llm_client.py](app/generation/llm_client.py)) works with
any OpenAI-compatible API; set `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`
(examples for OpenAI, Azure OpenAI, Mistral and Ollama in [.env.example](.env.example)).
Requests time out after `LLM_TIMEOUT` seconds and are retried once. Newer OpenAI models
reject `max_tokens`, so `LLM_TOKEN_PARAM=auto` sends `max_completion_tokens` for
openai/azure and `max_tokens` elsewhere.

## Evaluation

```bash
python eval/run_eval.py --retrieval-only   # retrieval metrics, no LLM calls (~7 min on CPU)
python eval/run_eval.py                    # full answers (40 LLM calls, ~8 min)
```

[eval/run_eval.py](eval/run_eval.py) runs the 40 acceptance questions in the collection's
`evaluation_questions.json` (not part of the corpus) and writes `eval/results/<run>.jsonl`
(answers, retrieved and cited sources, timings) and `<run>.md` (metrics table). Retrieval and
citation metrics are automatic. Factual support and whether a clarification or abstention was
appropriate were LLM-graded against each question's rubric and the source texts
(`eval/results/run*-review.md`); this is not a human review.

The run-by-run table is in [Results](#results) (hybrid_rerank, int8 ONNX reranker, 20
candidates, 256 tokens, `gpt-6-luna`; runs 1–4 on 19–20 November 2026). Files: `run1-full` …
`run4-full` and their reviews; run5 is `20261120-201349-full` (automatic metrics only). In
run4 only the 14 answers that changed or were partial in run3 were re-read (the same 14
scored 5 / 9 / 0 in run3); see `eval/results/run4-full-review.md`.

Retrieval modes compared on the same 40 questions (retrieval only, top 5, no LLM;
`eval/results/retrieval-<mode>.*`, 20 November 2026). "Top 1" means the first passage comes
from an expected source; scores are the best retrieval score of the lowest-scoring
answerable question and of the live-vacancy question Q40:

| Mode | Expected source in top 5 | All expected sources | Top 1 | MRR | Lowest answerable score | Q40 score |
|---|---|---|---|---|---|---|
| `bm25` | 35/38 | 29/38 | 23/38 | 0.73 | 5.26 | 4.99 |
| `dense` | 38/38 | 34/38 | 29/38 | 0.86 | 0.817 | 0.786 |
| `hybrid` | 37/38 | 34/38 | 29/38 | 0.85 | 0.0301 | 0.0328 |
| `hybrid_rerank` | 38/38 | 33/38 | 32/38 | 0.92 | 0.0295 | 0.0005 |

BM25 and dense scores have no fixed scale, and the hybrid RRF score depends only on ranks,
so only the reranker's 0–1 score separates Q40 from the answerable questions. Median
retrieval time per question on the laptop: under 0.1 s without the reranker, 10.3 s with it.

Known limitations:
- The reranker gives near-zero scores both to off-topic questions and to on-topic questions
  that the sources cannot answer (e.g. "Which dorm has an empty room today?", 0.0004), so the
  latter get the generic refusal instead of a pointer to the housing portal.
- Some answers leave out a detail the rubric expects (e.g. the previous tenant's right to the
  room, the validation terminal), and multi-source questions sometimes miss one source
  (Q13 without D04, Q29 without D30).
- The collection is a snapshot (captured 18 November 2026): fees, deadlines, contacts and
  visa rules must be refreshed before a new semester.

## Web app

Start the server (Windows, from the project folder), then open http://127.0.0.1:7860:

```bash
.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 7860
```

Startup takes ~25 s: the retriever, reranker and LLM client are loaded once (FastAPI
lifespan) and shared by all requests. Avoid `--reload`: every reload loads the ~3 GB of
models again.

| Endpoint             | What it does                                                      |
|----------------------|-------------------------------------------------------------------|
| `GET /`              | Chat page ([app/static/](app/static/), plain HTML/CSS/JS)          |
| `POST /api/ask`      | `{"question": "...", "mode": "hybrid_rerank"}` → answer, citations, `refused`, timings, `question_id` |
| `POST /api/feedback` | `{"question_id": "...", "helpful": true, "comment": "..."}`       |
| `GET /api/health`    | status, number of chunks/documents, loaded models                 |
| `GET /api/sources`   | all source documents (title, url, language)                       |

- Questions are limited to 500 characters; invalid requests get a JSON error
  `{"error": {"code", "message", "details"}}` (422), an unreachable LLM a 503.
- Rate limit per client IP: `RATE_LIMIT_PER_MINUTE` (10) questions and
  `FEEDBACK_RATE_LIMIT_PER_MINUTE` (30) feedback requests; over the limit → 429 with
  `Retry-After`. Behind a trusted proxy (e.g. Hugging Face Spaces) set
  `TRUST_FORWARDED_FOR=true` so the real client IP is used.
- Daily budget for all users together: `DAILY_QUESTION_LIMIT` (200) questions answered by
  the LLM per UTC day (greetings and below-threshold refusals do not count; LLM errors give
  the slot back). When it is used up, `/api/ask` returns 429 `daily_limit_reached` with a
  friendly message and `Retry-After` until 00:00 UTC. The count is kept in memory, so a
  restart also resets it; `/api/health` shows `questions_today`. 0 = no limit.
- Every question is logged to `logs/queries.jsonl` (id, timestamp, question, language,
  refused, refusal reason, best score, cited doc_ids, timings) and feedback to
  `logs/feedback.jsonl`. No IP addresses are logged. `logs/` is git-ignored.

## Docker and deployment

> **Hugging Face Spaces need a PRO plan.** As of November 2026, Docker Spaces require a paid
> Hugging Face PRO subscription, so Signpost is not deployed there for now. The Docker image
> runs on any Docker host; the Space files ([deploy/](deploy/),
> [scripts/deploy_space.ps1](scripts/deploy_space.ps1)) are kept for later. The reranker model
> repo is a free model repo and is used by every Docker build.

The [Dockerfile](Dockerfile) builds a CPU-only image (Python 3.12 slim, CPU PyTorch, non-root
user, port 7860). At build time it downloads the int8 ONNX reranker from the model repo
[MohammadBilalHabibi12345/signpost-reranker-onnx-int8](https://huggingface.co/MohammadBilalHabibi12345/signpost-reranker-onnx-int8)
and the e5 embedding model, ingests the collection and builds the index; at run time it makes
no Hub calls. The image is about 3–3.5 GB; the server needs 3–4 GB RAM.

Why a model repo for the 570 MB reranker: exporting it inside the build would add 5–8 minutes
and several GB of RAM to every build; Git LFS in the Space repo would re-push it with the code.
A model repo is uploaded once, versioned on its own, and downloaded in seconds by the build.

**One-time setup (Windows)**

1. Docker Desktop: in PowerShell as Administrator run `wsl --install --no-distribution`,
   restart, then `winget install -e --id Docker.DockerDesktop` (keep "Use WSL 2"), start
   Docker Desktop and check with `docker run hello-world`.
2. Hugging Face: create a token with **Write** access at
   https://huggingface.co/settings/tokens, then run `.venv\Scripts\hf.exe auth login`.
3. Upload the reranker once (done for this project; free) and create the Space (needs PRO):
   `powershell -ExecutionPolicy Bypass -File scripts\deploy_space.ps1 -UploadReranker`

**Build and run locally**

```bash
docker build -t signpost .
docker run --rm -p 7860:7860 --env-file .env signpost
```

Open http://127.0.0.1:7860 (startup takes about a minute while the models load).
`--env-file` passes values literally, so values in `.env` must not be in quotes.

**Space settings, if you deploy to a Space** (needs HF PRO; Settings → Variables and secrets;
the deploy script sets the variables):

| Name | Kind | Value |
|---|---|---|
| `LLM_API_KEY` | **secret** | your API key (set it yourself; never in a file or script) |
| `LLM_PROVIDER` | variable | `openai` |
| `LLM_BASE_URL` | variable | `https://api.openai.com/v1` |
| `LLM_MODEL` | variable | `gpt-6-luna` (the tested model; the code default is `gpt-4o-mini`) |
| `TRUST_FORWARDED_FOR` | variable | `true` (rate limit per real client IP behind the Space proxy) |
| `DAILY_QUESTION_LIMIT` | variable | `200` (optional; same as the default) |

All other settings use the tested code defaults. If answers are too slow, `RERANK_CANDIDATES=10`
roughly halves the reranking time (see the latency table above).

**Deploy / update**: `powershell -ExecutionPolicy Bypass -File scripts\deploy_space.ps1`
uploads only what the image needs (no PDFs, models, index or secrets; `-DryRun` lists the
files) and starts a build; follow it with
`.venv\Scripts\hf.exe spaces logs MohammadBilalHabibi12345/signpost --build -f`.

**Expected speed on a CPU basic Space** (2 vCPU): reranking takes about 9 s on the
4-core laptop used for development, so expect roughly 15–20 s there plus 2–3 s for the LLM,
**about 18–25 s per answer**. This is an estimate until measured (`timings_ms` in every
`/api/ask` response).

**CI**: [.github/workflows/ci.yml](.github/workflows/ci.yml) runs ruff and the fast tests
on every push and pull request (CPU PyTorch, no model downloads, no API key).
[.github/workflows/docker.yml](.github/workflows/docker.yml) builds the image on a Linux runner
whenever the Dockerfile, code or knowledge base changes, starts it and checks health, sources,
the chat page, small talk and one retrieval + reranking question (the LLM is pointed at an
unreachable address on purpose, so no API key is used and that question must return 503).

## Deployment on Azure Container Apps

Live: https://signpost.icyground-8b8d4d52.francecentral.azurecontainerapps.io

**How it fits together**

- **Image**: [.github/workflows/docker.yml](.github/workflows/docker.yml) builds the image on
  every push to `main` that changes the app, the image files or the sources, starts it, checks
  it, measures its memory and pushes it to the public package
  `ghcr.io/mohammadbilalhabibi/signpost` (`:latest` and `:<commit>`). For a commit that only
  changed other files, publish its image with GitHub → Actions → Docker → "Run workflow" on
  `main`. GitHub
  Container Registry is free and nothing large is uploaded from your machine. The Azure
  alternatives were building locally and pushing (several GB over a slow upload, and Docker
  Desktop needs a current WSL) or `az acr build` (simple, faster wake-up, but a Basic
  registry costs about 5 USD/month of credit).
- **Container App** `signpost` in resource group `signpost-rg`, region **France Central**
  (the Azure for Students policy only allows francecentral, norwayeast, polandcentral,
  belgiumcentral and switzerlandnorth), Consumption plan, **scale to zero** (min 0, max 1
  replica), external HTTPS ingress to port 7860. Definition: [deploy/containerapp.yaml](deploy/containerapp.yaml).
- **Size: 1.75 vCPU / 3.5 GiB.** Measured memory: 1.60 GiB after startup and a 2.07 GiB peak
  after 3 questions (`docker stats` on the GitHub runner, LLM unreachable), and a 2.44 GiB peak
  while answering 3 real questions on Azure (`WorkingSetBytes`). 1.75/3.5 is the smallest
  Consumption size with at least 25 % headroom (1.5/3.0 would leave 19 %).
- **Free grant**: 180,000 vCPU-seconds and 360,000 GiB-seconds per month give
  180,000 / 1.75 = 360,000 / 3.5 = **102,857 s ≈ 28.6 hours of running replica per month**.
  Idle time at zero replicas costs nothing; a woken replica stays up for the 300 s cooldown
  after the last request, so every visit uses at least about 5 minutes.
- **Settings**: secret `llm-api-key` (set from `.env` by the script, never printed) mapped to
  `LLM_API_KEY`; environment variables `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL=gpt-6-luna`,
  `TRUST_FORWARDED_FOR=true`, `DAILY_QUESTION_LIMIT=200`. Container Apps ingress appends the
  client address as the right-most `X-Forwarded-For` entry (Microsoft docs: "Only the
  rightmost IP is provided by Azure Container Apps"); the app uses the right-most public
  address, so client-supplied values cannot bypass the rate limit (tested live: 4 requests
  with different spoofed values, limit 3 → the 4th got 429).
- **Probes**: startup `GET /api/health` every 5 s for up to 10 minutes (model loading takes
  about a minute), readiness `GET /api/health`, liveness `GET /health`.
- **Costs**: no Log Analytics workspace (`--logs-destination none`); a monthly **budget of
  20 USD** with e-mail alerts at 50 % and 80 % (actual) and 100 % (forecast). Budgets only
  alert; they do not stop resources. Delete everything with
  `az group delete --name signpost-rg`.

**Deploy or update** (after `az login`; the script explains every `az` command):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_azure.ps1
```

It registers the resource providers, creates the resource group, the Consumption
environment and the app (or updates it), sets the secret, replaces the running replica and
creates the budget. A new image from GitHub Actions is used the next time a replica starts;
run the script again to switch immediately. Logs:
`az containerapp logs show -n signpost -g signpost-rg --follow`.

Note: `az containerapp env create` (CLI 2.93) creates an *express* environment, which does
not support revision restarts or revision suffixes; the script replaces the replica by
updating a `DEPLOYED_AT` environment variable instead.

If budgets are not available on a subscription: Azure portal → Cost Management →
Budgets → Add → scope: the subscription, amount 20, monthly, alert conditions 50/80/100 %,
your e-mail.

**Measured speed** (20 November 2026, 1.75 vCPU / 3.5 GiB): after the app had scaled to zero,
the first request answered after **20 s** (start + model loading; can be longer when Azure
starts the replica on a machine that has not cached the 5.4 GB image yet). Answers on the
running replica took **10.5–12 s** (about 9 s reranking, 2 s LLM); at 1.5 vCPU they took
10–16 s. The app scaled to zero about 5–8 minutes after the last request. A second
measurement later the same day (image `123cb00`): wake-up **14.2 s**, then answers in 9.9 s
and 8.8 s (about 6.9 s reranking, 1.8–2.5 s LLM).

## Layout

```
app/            api.py, config.py, ingest/, retrieval/, generation/, static/
DIT_Arrival_RAG_English/  source collection: sources.json, text/ copies, evaluation questions
data/raw/       downloads of the optional URL crawler (git-ignored)
data/processed/ cleaned documents and chunks (JSONL)
index/          FAISS + BM25 artifacts (git-ignored)
models/         exported int8 ONNX reranker (git-ignored)
eval/           evaluation runner and results
docs/           demo.gif (recorded on the live app with Playwright)
scripts/        CLI scripts (incl. deploy_space.ps1)
deploy/         Hugging Face Space README and reranker model card
tests/          pytest tests
```

## Configuration

All settings are read from environment variables / `.env`; see
[.env.example](.env.example) for the full list.
