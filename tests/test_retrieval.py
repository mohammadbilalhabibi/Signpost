"""Retrieval tests on a tiny in-memory corpus.

The default suite uses small deterministic fake models (fast, offline). The test
marked ``slow`` loads the real e5 + bge-reranker models: run it with ``pytest -m slow``.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np
import pytest

from app.retrieval.base import ChunkStore, Hit, Retriever, StaleIndexError
from app.retrieval.bm25 import BM25Retriever, tokenize
from app.retrieval.dense import PASSAGE_PREFIX, QUERY_PREFIX, DenseRetriever
from app.retrieval.factory import build_indexes, check_index
from app.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from app.retrieval.rerank import RerankedRetriever, to_probability


def chunk(chunk_id: str, title: str, section: str, body: str, language: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": chunk_id.rsplit("-", 1)[0],
        "title": title,
        "url": f"https://example.org/{chunk_id}",
        "language": language,
        "section": section,
        "text": f"{title} > {section}\n\n{body}",
        "n_tokens": 0,
    }


CORPUS = [
    chunk(
        "anmeldung-0000",
        "Stadt Deggendorf – Wohnsitz anmelden",
        "Anmeldung",
        "Wer nach Deggendorf zieht, muss den Wohnsitz innerhalb von zwei Wochen beim "
        "Bürgeramt anmelden. Mitzubringen sind Personalausweis und Wohnungsgeberbestätigung.",
        "de",
    ),
    chunk(
        "fees-0000",
        "THD – Gebühren",
        "Semesterbeitrag",
        "Der Semesterbeitrag beträgt 82 Euro pro Semester und wird bei der Rückmeldung fällig.",
        "de",
    ),
    chunk(
        "work-0000",
        "Working while studying",
        "Student jobs",
        "International students may work 140 full days or 280 half days per year. "
        "Students from the EU can work without restrictions.",
        "en",
    ),
    chunk(
        "insurance-0000",
        "Health insurance in Germany",
        "Public insurance",
        "All students in Germany need health insurance. Public health insurance costs "
        "about 140 euros per month.",
        "en",
    ),
    chunk(
        "housing-0000",
        "Studierendenwerk – Wohnen",
        "Wohnheime",
        "Das Studierendenwerk vermietet Zimmer in vier Wohnheimen in Deggendorf. "
        "Die Miete liegt bei 250 bis 400 Euro.",
        "de",
    ),
    chunk(
        "exams-0000",
        "Examination regulations",
        "§ 12 Exam registration",
        "Students must register for exams in Primuss during the registration period. "
        "Withdrawal is possible until 6 days before the exam.",
        "en",
    ),
]

QUESTIONS = [
    ("Wie hoch ist der Semesterbeitrag?", "fees-0000"),
    ("Wo muss ich meinen Wohnsitz in Deggendorf anmelden?", "anmeldung-0000"),
    ("Can international students work during their studies?", "work-0000"),
    ("How much does public health insurance cost?", "insurance-0000"),
]
MODES = ["bm25", "dense", "hybrid", "hybrid_rerank"]


# ------------------------------------------------------------------- fake models


class FakeEncoder:
    """Hashed bag-of-words vectors: deterministic, offline, good enough for exact words."""

    dim = 256

    def encode(self, sentences: list[str], **kwargs) -> np.ndarray:
        out = np.zeros((len(sentences), self.dim), dtype=np.float32)
        for row, text in enumerate(sentences):
            text = text.removeprefix(QUERY_PREFIX).removeprefix(PASSAGE_PREFIX)
            for token in tokenize(text):
                out[row, zlib.crc32(token.encode("utf-8")) % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-12)


class FakeCrossEncoder:
    """Score = share of query tokens found in the passage (already in 0-1)."""

    def __init__(self) -> None:
        self.calls = 0

    def predict(self, sentences: list[tuple[str, str]], **kwargs) -> np.ndarray:
        self.calls += 1
        scores = []
        for query, passage in sentences:
            q, p = set(tokenize(query)), set(tokenize(passage))
            scores.append(len(q & p) / len(q) if q else 0.0)
        return np.array(scores)


def make_retrievers(chunks: list[dict], encoder=None, cross_encoder=None) -> dict[str, Retriever]:
    store = ChunkStore(chunks)
    dense = DenseRetriever.build(store, encoder or FakeEncoder())
    bm25 = BM25Retriever.build(store)
    hybrid = HybridRetriever([dense, bm25], candidates=20, rrf_k=60)
    rerank = RerankedRetriever(hybrid, cross_encoder or FakeCrossEncoder(), candidates=20)
    return {"bm25": bm25, "dense": dense, "hybrid": hybrid, "hybrid_rerank": rerank}


@pytest.fixture(scope="module")
def retrievers() -> dict[str, Retriever]:
    return make_retrievers(CORPUS)


# ------------------------------------------------------------------ every mode


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(("question", "expected"), QUESTIONS)
def test_each_mode_finds_the_obvious_chunk(
    retrievers: dict[str, Retriever], mode: str, question: str, expected: str
) -> None:
    hits = retrievers[mode].search(question, k=3)
    assert hits, f"{mode} returned nothing"
    assert hits[0].chunk_id == expected


@pytest.mark.parametrize("mode", MODES)
def test_hits_carry_metadata_and_respect_k(retrievers: dict[str, Retriever], mode: str) -> None:
    hits = retrievers[mode].search("Can students work in Germany?", k=2)
    assert 1 <= len(hits) <= 2
    for hit in hits:
        source = next(c for c in CORPUS if c["chunk_id"] == hit.chunk_id)
        assert (hit.doc_id, hit.title, hit.url, hit.language, hit.text) == (
            source["doc_id"],
            source["title"],
            source["url"],
            source["language"],
            source["text"],
        )
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


@pytest.mark.parametrize("mode", MODES)
def test_k_zero_returns_nothing(retrievers: dict[str, Retriever], mode: str) -> None:
    assert retrievers[mode].search("Semesterbeitrag", k=0) == []


# ------------------------------------------------------------------------ BM25


def test_tokenizer_keeps_umlauts_and_drops_stopwords() -> None:
    assert tokenize("Die Größe der Prüfungsämter ist ÜBERALL gleich.") == [
        "größe",
        "prüfungsämter",
        "überall",
        "gleich",
    ]
    assert tokenize("How do I register my address?") == ["register", "address"]


def test_tokenizer_keeps_numbers() -> None:
    assert "12" in tokenize("§ 12")
    assert tokenize("6 Monate") == ["6", "monate"]


def test_bm25_skips_chunks_without_matching_terms(retrievers: dict[str, Retriever]) -> None:
    hits = retrievers["bm25"].search("Semesterbeitrag", k=6)
    assert [h.chunk_id for h in hits] == ["fees-0000"]
    assert retrievers["bm25"].search("der die das", k=5) == []  # only stopwords


# ------------------------------------------------------------------------ dense


def test_dense_scores_are_cosine_similarities(retrievers: dict[str, Retriever]) -> None:
    hits = retrievers["dense"].search("Semesterbeitrag 82 Euro", k=6)
    assert len(hits) == 6  # dense always ranks every chunk
    assert all(-1.0 - 1e-5 <= h.score <= 1.0 + 1e-5 for h in hits)


# ------------------------------------------------------------------------- RRF


def test_rrf_scores_and_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "d"]], k=60)
    assert [cid for cid, _ in fused] == ["b", "c", "a", "d"]
    scores = dict(fused)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["c"] == pytest.approx(1 / 63 + 1 / 62)
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["d"] == pytest.approx(1 / 63)


def test_rrf_item_in_both_lists_beats_single_top_item() -> None:
    fused = reciprocal_rank_fusion([["solo", "both"], ["x", "y", "both"]], k=60)
    assert fused[0][0] == "both"  # 1/62 + 1/63 > 1/61


def test_rrf_ties_are_deterministic() -> None:
    assert [c for c, _ in reciprocal_rank_fusion([["b"], ["a"]])] == ["a", "b"]
    assert [c for c, _ in reciprocal_rank_fusion([["a", "b"], ["b", "a"]])] == ["a", "b"]


class StubRetriever(Retriever):
    def __init__(self, store: ChunkStore, ids: list[str]) -> None:
        self.store, self.ids = store, ids

    def search(self, query: str, k: int) -> list[Hit]:
        return [self.store.hit(cid, 1.0) for cid in self.ids[:k]]


def test_hybrid_merges_with_rrf() -> None:
    store = ChunkStore(CORPUS)
    first = StubRetriever(store, ["fees-0000", "work-0000", "exams-0000"])
    second = StubRetriever(store, ["work-0000", "housing-0000"])
    hits = HybridRetriever([first, second], candidates=20, rrf_k=60).search("q", k=10)
    assert [h.chunk_id for h in hits] == ["work-0000", "fees-0000", "housing-0000", "exams-0000"]
    assert hits[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert hits[1].score == pytest.approx(1 / 61)


def test_hybrid_asks_sub_retrievers_for_at_least_k() -> None:
    store = ChunkStore(CORPUS)
    seen: list[int] = []

    class Recording(StubRetriever):
        def search(self, query: str, k: int) -> list[Hit]:
            seen.append(k)
            return super().search(query, k)

    HybridRetriever([Recording(store, [])], candidates=20).search("q", k=30)
    assert seen == [30]


# ---------------------------------------------------------------------- rerank


def padded_corpus(n_fillers: int) -> list[dict]:
    fillers = [
        chunk(f"filler-{i:04d}", f"Filler {i}", "Students", f"Students note number {i}.", "en")
        for i in range(n_fillers)
    ]
    return CORPUS + fillers


def test_rerank_returns_k10_for_evaluation() -> None:
    reranked = make_retrievers(padded_corpus(8))["hybrid_rerank"]  # 14 chunks
    hits = reranked.search("Can international students work?", k=10)
    assert len(hits) == 10
    assert hits[0].chunk_id == "work-0000"
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert all(0.0 <= h.score <= 1.0 for h in hits)


def test_rerank_returns_all_candidates_when_k_exceeds_them() -> None:
    reranked = make_retrievers(padded_corpus(8))["hybrid_rerank"]
    assert len(reranked.search("students", k=50)) == 14


def test_rerank_returns_k5_for_answers(retrievers: dict[str, Retriever]) -> None:
    assert len(retrievers["hybrid_rerank"].search("students", k=5)) == 5


def test_to_probability_maps_logits_to_unit_interval() -> None:
    probs = to_probability(np.array([-3.0, 0.0, 4.0]))
    assert probs[1] == pytest.approx(0.5)
    assert np.all((probs > 0) & (probs < 1)) and probs[0] < probs[2]


# ------------------------------------------------------------ save / load / stale


def test_indexes_round_trip_and_detect_stale_chunks(tmp_path: Path) -> None:
    store = ChunkStore(CORPUS)
    encoder = FakeEncoder()
    build_indexes(store, tmp_path, encoder, model_name="fake-model")
    assert check_index(tmp_path, store)["chunks"] == 6

    bm25 = BM25Retriever.load(tmp_path, store)
    dense = DenseRetriever.load(tmp_path, store, encoder, model_name="fake-model")
    assert bm25.search("Semesterbeitrag", 1)[0].chunk_id == "fees-0000"
    assert dense.search("Semesterbeitrag", 1)[0].chunk_id == "fees-0000"

    changed = ChunkStore([*CORPUS[:5], {**CORPUS[5], "text": CORPUS[5]["text"] + " Neu."}])
    with pytest.raises(StaleIndexError):
        check_index(tmp_path, changed)
    with pytest.raises(StaleIndexError):
        BM25Retriever.load(tmp_path, ChunkStore(CORPUS[:5]))
    with pytest.raises(StaleIndexError):
        DenseRetriever.load(tmp_path, store, encoder, model_name="another-model")


def test_missing_index_is_reported(tmp_path: Path) -> None:
    with pytest.raises(StaleIndexError, match="build_index"):
        check_index(tmp_path, ChunkStore(CORPUS))


# ------------------------------------------------------------- real models (slow)


@pytest.mark.slow
def test_real_models_find_the_obvious_chunk() -> None:
    from app.config import get_settings
    from app.retrieval.factory import load_embedding_model, load_reranker

    settings = get_settings()
    real = make_retrievers(
        CORPUS,
        encoder=load_embedding_model(settings.embedding_model),
        cross_encoder=load_reranker(settings.reranker_model),
    )
    for question, expected in QUESTIONS:
        for mode in MODES:
            hits = real[mode].search(question, k=3)
            assert hits[0].chunk_id == expected, (mode, question, [h.chunk_id for h in hits])
    assert all(0.0 <= h.score <= 1.0 for h in real["hybrid_rerank"].search("Wohnheim", 5))
