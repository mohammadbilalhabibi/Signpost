"""Tests for answer generation with a fake LLM (no network, no real models)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import numpy as np
import openai
import pytest

from app.config import Settings
from app.generation.llm_client import GenerationError, LLMClient, LLMResult
from app.generation.pipeline import (
    AnswerPipeline,
    Citation,
    group_sources,
    limit_per_document,
    make_snippet,
    parse_citations,
    response_language,
)
from app.generation.prompts import (
    REFUSAL_TEXT,
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_response_type,
)
from app.generation.smalltalk import REPLIES, detect_smalltalk
from app.retrieval.base import Hit, Retriever
from app.retrieval.rerank import RerankedRetriever
from tests.test_retrieval import CORPUS, make_retrievers

# ------------------------------------------------------------------- fakes


class FakeLLM:
    """Returns a canned reply and records every call."""

    def __init__(self, text: str = "Answer [1].") -> None:
        self.text = text
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResult:
        self.calls.append((system, user))
        return LLMResult(text=self.text, model="fake-llm", finish_reason="stop")


class StaticRetriever(Retriever):
    """Always returns the same hits (in this order)."""

    name = "static"

    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits

    def search(self, query: str, k: int) -> list[Hit]:
        return self.hits[:k]


class FixedScores:
    """Cross-encoder stand-in: the i-th pair gets scores[i]."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def predict(self, sentences, **kwargs) -> np.ndarray:
        return np.array(self.scores[: len(sentences)])


def make_hit(i: int) -> Hit:
    return Hit(
        chunk_id=f"doc{i}-0000",
        doc_id=f"doc{i}",
        score=0.0,
        text=f"Source {i} > Section\n\nBody text of source number {i} about student life.",
        title=f"Source {i}",
        url=f"https://example.org/{i}",
        language="en",
    )


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{"refusal_threshold": 0.1, **overrides})


def reranked_pipeline(scores: list[float], llm: FakeLLM, **overrides) -> AnswerPipeline:
    hits = [make_hit(i) for i in range(1, len(scores) + 1)]
    retriever = RerankedRetriever(StaticRetriever(hits), FixedScores(scores), candidates=10)
    return AnswerPipeline(retriever, llm, settings(**overrides), mode="hybrid_rerank")


FIVE_SCORES = [0.9, 0.8, 0.7, 0.6, 0.5]

# ---------------------------------------------------------------- citations


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Claim [1]. Other claim [3].", [1, 3]),
        ("Both say so [1, 3]; see also [2][4].", [1, 2, 3, 4]),
        ("A range [1-3] and [5].", [1, 2, 3, 5]),
        ("Out of range [7], [0] and a year [2024] are ignored [2].", [2]),
        ("No citation at all.", []),
        ("Duplicates [2] [2] [2].", [2]),
    ],
)
def test_parse_citations(text: str, expected: list[int]) -> None:
    assert parse_citations(text, 5) == expected


def test_only_cited_sources_are_returned_with_metadata() -> None:
    llm = FakeLLM("Register within two weeks [2]. Bring your passport [4][2].")
    result = reranked_pipeline(FIVE_SCORES, llm).answer("How do I register?")

    assert [c.number for c in result.citations] == [2, 4]
    first = result.citations[0]
    assert (first.title, first.url) == ("Source 2", "https://example.org/2")
    assert first.snippet.startswith("Body text of source number 2")  # header removed
    assert result.refused is False and result.refusal_reason is None
    assert result.model == "fake-llm" and len(llm.calls) == 1


def test_passages_of_one_document_become_one_source() -> None:
    hits = [make_hit(1), make_hit(2), Hit(**{**make_hit(1).__dict__, "chunk_id": "doc1-0001"})]
    retriever = RerankedRetriever(StaticRetriever(hits), FixedScores([0.9, 0.8, 0.7]))
    llm = FakeLLM("Register within two weeks [1]. Bring a passport [3]. Fees differ [2].")
    result = AnswerPipeline(retriever, llm, settings()).answer("How do I register?")

    assert [c.number for c in result.citations] == [1, 2, 3]  # per passage, unchanged
    assert [(s.numbers, s.doc_id) for s in result.sources] == [((1, 3), "doc1"), ((2,), "doc2")]
    first = result.sources[0]
    assert (first.title, first.url, first.language) == ("Source 1", "https://example.org/1", "en")
    assert first.snippet.startswith("Body text of source number 1")
    assert result.to_dict()["sources"][0]["numbers"] == (1, 3)


def test_group_sources_orders_by_first_citation_number() -> None:
    def cite(number: int, doc: str) -> Citation:
        return Citation(number, f"T{doc}", f"https://x/{doc}", "s", doc, "de")

    sources = group_sources([cite(4, "b"), cite(2, "a"), cite(1, "b"), cite(5, "a")])
    assert [(s.doc_id, s.numbers) for s in sources] == [("b", (1, 4)), ("a", (2, 5))]
    assert group_sources([]) == []


def test_numbers_beyond_the_passages_are_dropped() -> None:
    llm = FakeLLM("Only five passages exist [1] [6].")
    result = reranked_pipeline(FIVE_SCORES, llm).answer("Question?")
    assert [c.number for c in result.citations] == [1]


def test_not_found_reply_counts_as_refused() -> None:
    llm = FakeLLM("TYPE: not_found\nThe passages do not say. Please ask the Welcome Centre.")
    result = reranked_pipeline(FIVE_SCORES, llm).answer("What is the visa fee?")
    assert result.refused is True
    assert result.response_type == "not_found"
    assert result.refusal_reason == "not_in_sources"
    assert result.answer.startswith("The passages do not say")  # TYPE line removed
    assert result.citations == []


def test_clarify_reply_is_not_a_refusal() -> None:
    llm = FakeLLM("TYPE: clarify\nEU students pay X [1], non-EU students Y [2]. Which applies?")
    result = reranked_pipeline(FIVE_SCORES, llm).answer("Which fees do I pay?")
    assert result.response_type == "clarify" and result.refused is False
    assert [c.number for c in result.citations] == [1, 2]


@pytest.mark.parametrize(
    ("reply", "kind", "text"),
    [
        ("TYPE: answer\nYes [1].", "answer", "Yes [1]."),
        ("**TYPE: clarify**\nWhich semester?", "clarify", "Which semester?"),
        ("TYPE: Not Found\nNo.", "not_found", "No."),
        ("TYPE: weird\nHm.", "answer", "Hm."),
        ("No type line [1].", "answer", "No type line [1]."),
    ],
)
def test_parse_response_type(reply: str, kind: str, text: str) -> None:
    assert parse_response_type(reply) == (kind, text)


def test_retrieved_chunks_are_reported() -> None:
    result = reranked_pipeline(FIVE_SCORES, FakeLLM()).answer("Question?")
    assert [r["doc_id"] for r in result.retrieved] == ["doc1", "doc2", "doc3", "doc4", "doc5"]
    assert result.retrieved[0]["score"] == pytest.approx(0.9)


def test_snippet_is_cut_at_a_word_boundary() -> None:
    hit = make_hit(1)
    long_hit = Hit(**{**hit.__dict__, "text": "Title > S\n\n" + "word " * 100})
    snippet = make_snippet(long_hit, max_chars=50)
    assert snippet.endswith(" …") and len(snippet) <= 52
    assert "Title" not in snippet


# ----------------------------------------------------------------- refusals


def test_low_score_refuses_without_calling_the_llm() -> None:
    llm = FakeLLM()
    result = reranked_pipeline([0.05, 0.01], llm).answer("What is the best pizza in Munich?")
    assert result.refused is True
    assert result.refusal_reason == "low_score"
    assert result.answer == REFUSAL_TEXT["en"]
    assert result.citations == [] and result.sources == []
    assert llm.calls == []
    assert result.timings_ms["generation"] is None
    assert result.best_score == pytest.approx(0.05)


def test_refusal_is_english_by_default_even_for_german_questions() -> None:
    llm = FakeLLM()
    result = reranked_pipeline([0.05], llm).answer("Wo gibt es die beste Pizza in München?")
    assert result.language == "en"
    assert result.answer == REFUSAL_TEXT["en"]
    assert llm.calls == []


def test_refusal_is_german_when_explicitly_requested() -> None:
    result = reranked_pipeline([0.05], FakeLLM()).answer("Beste Pizza? Bitte auf Deutsch.")
    assert result.language == "de" and result.answer == REFUSAL_TEXT["de"]


@pytest.mark.parametrize("message", ["Hi! I am new here.", "hello", "Thanks!", "bye"])
def test_smalltalk_is_answered_without_retrieval_or_llm(message: str) -> None:
    class ExplodingRetriever(StaticRetriever):
        def search(self, query: str, k: int) -> list[Hit]:
            raise AssertionError("retrieval must not run for small talk")

    llm = FakeLLM()
    result = AnswerPipeline(ExplodingRetriever([]), llm, settings()).answer(message)
    assert result.response_type == "smalltalk" and result.refused is False
    assert result.citations == [] and llm.calls == []
    assert result.answer in REPLIES.values()


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("Hi! I am new here.", "greeting"),
        ("Good morning", "greeting"),
        ("Hi there, nice to meet you", "greeting"),
        ("thank you so much", "thanks"),
        ("Hello, how do I enrol?", None),
        ("Hey, I am new here. Where is the Welcome Centre?", None),
        ("History of Deggendorf", None),
        ("Which dorm has an empty room available today?", None),
    ],
)
def test_detect_smalltalk(message: str, kind: str | None) -> None:
    assert detect_smalltalk(message) == kind


def test_score_at_threshold_is_answered() -> None:
    llm = FakeLLM()
    result = reranked_pipeline([0.1], llm).answer("Question?")
    assert result.refused is False and len(llm.calls) == 1


def test_no_hits_refuses() -> None:
    llm = FakeLLM()
    pipeline = AnswerPipeline(StaticRetriever([]), llm, settings())
    result = pipeline.answer("Anything?")
    assert result.refused is True and result.refusal_reason == "no_hits"
    assert llm.calls == []


def test_threshold_is_skipped_for_modes_without_reranker() -> None:
    llm = FakeLLM()
    hits = [Hit(**{**make_hit(1).__dict__, "score": 0.016})]  # RRF-sized score
    pipeline = AnswerPipeline(StaticRetriever(hits), llm, settings())
    result = pipeline.answer("Question?")
    assert result.refused is False and len(llm.calls) == 1
    assert result.timings_ms["reranking"] is None


def test_empty_question_is_rejected() -> None:
    with pytest.raises(ValueError):
        reranked_pipeline(FIVE_SCORES, FakeLLM()).answer("   ")


# ------------------------------------------------------- prompt and timings


def test_llm_gets_numbered_passages_and_the_question() -> None:
    llm = FakeLLM()
    reranked_pipeline(FIVE_SCORES, llm).answer("How do I register?")
    system, user = llm.calls[0]
    assert system == SYSTEM_PROMPT
    for i in range(1, 6):
        assert f"[{i}] Source {i}" in user
    assert user.startswith("Today's date: ")
    assert user.rstrip().endswith("Question: How do I register?")


def test_passages_carry_source_metadata_and_links() -> None:
    meta = {
        "source_id": "D30",
        "publisher": "Stadt Deggendorf",
        "edition_or_period": "Summer semester 2027",
        "source_document_date": "2026-10-01",
        "source_format": "translated_summary",
        "source_language": "de",
        "note": "Original German page is authoritative.",
        "links": [{"text": "City form", "url": "https://example.org/form"}],
    }
    hit = Hit(**{**make_hit(1).__dict__, "meta": meta})
    prompt = build_user_prompt("Q?", [hit], today=date(2026, 11, 18))
    assert prompt.startswith("Today's date: 2026-11-18")
    assert "[1] D30 · Source 1 — Stadt Deggendorf" in prompt
    assert "Period: Summer semester 2027" in prompt and "Document date: 2026-10-01" in prompt
    assert "Format: translated summary (original language de)" in prompt
    assert "Source note: Original German page is authoritative." in prompt
    assert "Links: City form: https://example.org/form" in prompt


def test_prompt_uses_top_k_final_passages() -> None:
    llm = FakeLLM()
    reranked_pipeline([0.9] * 8, llm, top_k_final=3).answer("Question?")
    assert "[3] Source" in llm.calls[0][1] and "[4] Source" not in llm.calls[0][1]


def test_timings_cover_every_stage() -> None:
    result = reranked_pipeline(FIVE_SCORES, FakeLLM()).answer("Question?")
    assert set(result.timings_ms) == {"retrieval", "reranking", "generation", "total"}
    assert all(v is not None and v >= 0 for v in result.timings_ms.values())
    assert result.to_dict()["citations"][0]["number"] == 1


def test_pipeline_on_the_fake_corpus() -> None:
    retriever = make_retrievers(CORPUS)["hybrid_rerank"]
    llm = FakeLLM("82 Euro [1].")
    result = AnswerPipeline(retriever, llm, settings()).answer("Wie hoch ist der Semesterbeitrag?")
    assert result.citations[0].url == "https://example.org/fees-0000"
    assert result.mode == "hybrid_rerank" and result.language == "en"


def test_rerank_split_gives_the_same_result_as_search() -> None:
    reranked = make_retrievers(CORPUS)["hybrid_rerank"]
    query = "Can international students work?"
    split = reranked.rerank(query, reranked.inner.search(query, 20), 5)
    assert split == reranked.search(query, 5)


def test_build_user_prompt_strips_whitespace() -> None:
    assert build_user_prompt("  Q?  ", [make_hit(1)]).endswith("Question: Q?")


@pytest.mark.parametrize(
    ("question", "language"),
    [
        ("How do I register my address in Deggendorf?", "en"),
        ("Wie hoch ist der Semesterbeitrag?", "en"),  # English by default
        ("Please answer in German: how do I enrol?", "de"),
        ("Kannst du auf Deutsch antworten?", "de"),
        ("Is the course in German?", "en"),
    ],
)
def test_response_language(question: str, language: str) -> None:
    assert response_language(question) == language


# ---------------------------------------------------------------- LLM client


def fake_sdk(create) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def response(content: str | None, finish: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
        model="served-model",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
    )


def test_openai_provider_uses_max_completion_tokens() -> None:
    client = LLMClient(settings(llm_provider="openai", llm_api_key="sk-test"))
    assert isinstance(client.client, openai.OpenAI)
    kwargs = client.request_kwargs("sys", "user")
    assert kwargs["max_completion_tokens"] == 600
    assert "max_tokens" not in kwargs and "temperature" not in kwargs
    assert client.client.timeout == 30.0 and client.client.max_retries == 1


def test_azure_provider_uses_azure_client() -> None:
    client = LLMClient(
        settings(
            llm_provider="azure",
            llm_base_url="https://my-resource.openai.azure.com",
            llm_api_key="azure-key",
            llm_model="my-deployment",
        )
    )
    assert isinstance(client.client, openai.AzureOpenAI)
    assert client.token_param == "max_completion_tokens"


@pytest.mark.parametrize("provider", ["mistral", "ollama", "groq"])
def test_other_providers_use_max_tokens(provider: str) -> None:
    client = LLMClient(settings(llm_provider=provider, llm_base_url="http://localhost:11434/v1"))
    assert client.token_param == "max_tokens"


def test_token_param_and_temperature_can_be_overridden() -> None:
    client = LLMClient(
        settings(llm_provider="mistral", llm_token_param="max_completion_tokens",
                 llm_temperature=0.2)
    )  # fmt: skip
    kwargs = client.request_kwargs("sys", "user")
    assert kwargs["max_completion_tokens"] == 600 and kwargs["temperature"] == 0.2


def test_missing_key_gets_a_placeholder_for_ollama() -> None:
    client = LLMClient(settings(llm_provider="ollama", llm_base_url="http://localhost:11434/v1"))
    assert client.client.api_key == "not-needed"


def test_complete_returns_text_and_usage() -> None:
    calls = []
    sdk = fake_sdk(lambda **kw: calls.append(kw) or response(" Hallo! "))
    result = LLMClient(settings(llm_model="m"), client=sdk).complete("sys", "user")
    assert result.text == "Hallo!" and result.model == "served-model"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 3}
    assert calls[0]["messages"][0] == {"role": "system", "content": "sys"}


def test_empty_reply_raises_with_hint() -> None:
    sdk = fake_sdk(lambda **kw: response("", finish="length"))
    with pytest.raises(GenerationError, match="LLM_MAX_OUTPUT_TOKENS"):
        LLMClient(settings(), client=sdk).complete("sys", "user")


def test_sdk_errors_never_leak_the_key() -> None:
    secret = "sk-very-secret-key-123"

    def fail(**kwargs):
        raise openai.APIConnectionError(
            message=f"could not connect with key {secret}",
            request=httpx.Request("POST", "https://example.org"),
        )

    with pytest.raises(GenerationError) as info:
        LLMClient(settings(llm_api_key=secret), client=fake_sdk(fail)).complete("s", "u")
    assert secret not in str(info.value) and "[REDACTED]" in str(info.value)


# ------------------------------------------------------- per-document cap


def hit_of(doc: str, n: int, score: float) -> Hit:
    return Hit(f"{doc}-{n:04d}", doc, score, "t", doc, f"https://x/{doc}", "en")


def test_limit_per_document_keeps_other_sources() -> None:
    hits = [hit_of("D08", i, 0.9 - i / 100) for i in range(5)] + [
        hit_of("D14", 0, 0.5),
        hit_of("D15", 0, 0.4),
    ]
    chosen = limit_per_document(hits, k=5, cap=3)
    assert [h.doc_id for h in chosen] == ["D08", "D08", "D08", "D14", "D15"]


def test_limit_per_document_fills_up_when_few_documents() -> None:
    hits = [hit_of("D02", i, 0.9 - i / 100) for i in range(5)] + [hit_of("D04", 0, 0.95)]
    chosen = limit_per_document(hits, k=5, cap=3)
    assert len(chosen) == 5
    assert [h.score for h in chosen] == sorted((h.score for h in chosen), reverse=True)


def test_limit_per_document_can_be_disabled() -> None:
    hits = [hit_of("D08", i, 0.9 - i / 100) for i in range(6)]
    assert limit_per_document(hits, k=5, cap=0) == hits[:5]
