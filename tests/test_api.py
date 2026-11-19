"""API tests with FastAPI's TestClient and a fake pipeline (no models, no network)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import Services, create_app, list_sources
from app.config import Settings
from app.generation.llm_client import GenerationError
from app.generation.pipeline import Answer, Citation, group_sources
from app.retrieval.base import ChunkStore
from tests.test_retrieval import CORPUS

# ------------------------------------------------------------------- fakes


class FakePipeline:
    """Returns a canned answer citing the fees chunk; records the questions it got."""

    def __init__(self, mode: str, fail: bool = False) -> None:
        self.mode = mode
        self.fail = fail
        self.questions: list[str] = []

    def answer(self, question: str) -> Answer:
        self.questions.append(question)
        if self.fail:
            raise GenerationError("LLM request failed: boom")
        refused = "pizza" in question.lower()
        citations = (
            []
            if refused
            else [
                Citation(1, "THD – Gebühren", "https://example.org/fees-0000", "Der …",
                         "fees", "de"),
                Citation(2, "Health insurance", "https://example.org/ins", "All …",
                         "insurance", "en"),
                Citation(3, "THD – Gebühren", "https://example.org/fees-0000", "Die …",
                         "fees", "de"),
            ]
        )  # fmt: skip
        return Answer(
            question=question,
            answer="Not in my sources." if refused else "82 Euro [1][3]. Insured [2].",
            citations=citations,
            refused=refused,
            mode=self.mode,
            language="en",
            best_score=0.01 if refused else 0.9,
            timings_ms={"retrieval": 10.0, "reranking": 20.0, "generation": None if refused
                        else 30.0, "total": 60.0},
            refusal_reason="low_score" if refused else None,
            model=None if refused else "fake-llm",
            sources=group_sources(citations),
        )  # fmt: skip


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def made() -> dict[str, FakePipeline]:
    return {}


def make_client(
    tmp_path: Path,
    made: dict[str, FakePipeline],
    fail: bool = False,
    now: Callable[[], datetime] | None = None,
    **overrides,
) -> tuple[TestClient, Clock]:
    settings = Settings(_env_file=None, logs_dir=tmp_path / "logs", **overrides)

    def loader(_: Settings) -> Services:
        def make_pipeline(mode: str) -> FakePipeline:
            made[mode] = FakePipeline(mode, fail=fail)
            return made[mode]

        return Services(ChunkStore(CORPUS), make_pipeline, {"llm": "fake/fake-llm"})

    clock = Clock()
    extra = {"now": now} if now else {}
    return TestClient(create_app(settings, loader=loader, clock=clock, **extra)), clock


@pytest.fixture
def client(tmp_path: Path, made: dict[str, FakePipeline]) -> Iterator[TestClient]:
    test_client, _ = make_client(tmp_path, made)
    with test_client:
        yield test_client


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ------------------------------------------------------------------ startup


def test_default_pipeline_is_built_once_at_startup(
    client: TestClient, made: dict[str, FakePipeline]
) -> None:
    assert list(made) == ["hybrid_rerank"]
    client.post("/api/ask", json={"question": "Wie hoch ist der Semesterbeitrag?"})
    client.post("/api/ask", json={"question": "Second question?"})
    assert list(made) == ["hybrid_rerank"]
    assert len(made["hybrid_rerank"].questions) == 2


def test_health_reports_chunks_and_models(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["chunks"] == len(CORPUS)
    assert body["documents"] == len(CORPUS)
    assert body["models_loaded"] is True
    assert body["models"] == {"llm": "fake/fake-llm"}
    assert body["modes_loaded"] == ["hybrid_rerank"]
    assert body["questions_today"] == 0
    assert body["daily_question_limit"] == 200


def test_liveness_probe_works_without_models() -> None:
    from app.api import app

    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_api_returns_503_before_models_are_loaded(tmp_path: Path) -> None:
    app = create_app(Settings(_env_file=None, logs_dir=tmp_path))
    response = TestClient(app).get("/api/health")  # no `with`: lifespan not run
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"


# ---------------------------------------------------------------------- ask


def test_ask_returns_pipeline_result_with_question_id(client: TestClient) -> None:
    response = client.post("/api/ask", json={"question": "  Wie hoch ist der Semesterbeitrag? "})
    assert response.status_code == 200
    body = response.json()
    assert len(body["question_id"]) == 32
    assert body["answer"] == "82 Euro [1][3]. Insured [2]."
    assert body["question"] == "Wie hoch ist der Semesterbeitrag?"  # stripped
    assert body["citations"][0] == {
        "number": 1,
        "title": "THD – Gebühren",
        "url": "https://example.org/fees-0000",
        "snippet": "Der …",
        "doc_id": "fees",
        "language": "de",
    }
    # one source card per document, carrying all its citation numbers
    assert body["sources"] == [
        {
            "numbers": [1, 3],
            "doc_id": "fees",
            "title": "THD – Gebühren",
            "url": "https://example.org/fees-0000",
            "language": "de",
            "snippet": "Der …",
        },
        {
            "numbers": [2],
            "doc_id": "insurance",
            "title": "Health insurance",
            "url": "https://example.org/ins",
            "language": "en",
            "snippet": "All …",
        },
    ]
    assert body["refused"] is False
    assert body["timings_ms"]["total"] == 60.0


def test_ask_logs_every_question(client: TestClient, tmp_path: Path) -> None:
    first = client.post("/api/ask", json={"question": "Semesterbeitrag?"}).json()
    client.post("/api/ask", json={"question": "Best pizza in Munich?"})

    records = read_jsonl(tmp_path / "logs" / "queries.jsonl")
    assert len(records) == 2
    answered, refused = records
    assert answered["id"] == first["question_id"]
    assert answered["question"] == "Semesterbeitrag?"
    assert answered["cited_doc_ids"] == ["fees", "insurance"]
    assert answered["refused"] is False and answered["refusal_reason"] is None
    assert answered["best_score"] == 0.9 and answered["language"] == "en"
    assert answered["timings_ms"]["generation"] == 30.0
    assert answered["timestamp"].endswith("+00:00")
    assert refused["refused"] is True and refused["refusal_reason"] == "low_score"
    assert refused["cited_doc_ids"] == []


def test_mode_is_passed_to_the_pipeline(client: TestClient, made: dict[str, FakePipeline]) -> None:
    body = client.post("/api/ask", json={"question": "Q?", "mode": "bm25"}).json()
    assert body["mode"] == "bm25"
    assert made["bm25"].questions == ["Q?"]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"question": "x" * 501}, "question"),
        ({"question": "   "}, "question"),
        ({}, "question"),
        ({"question": "Q?", "mode": "magic"}, "mode"),
        ({"question": "Q?", "extra": 1}, "extra"),
    ],
)
def test_invalid_questions_get_clear_json_errors(
    client: TestClient, payload: dict, field: str
) -> None:
    response = client.post("/api/ask", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"][0]["field"] == field
    assert field in error["message"]


def test_question_of_exactly_500_characters_is_accepted(client: TestClient) -> None:
    assert client.post("/api/ask", json={"question": "x" * 500}).status_code == 200


def test_malformed_json_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/ask", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "not valid JSON" in response.json()["error"]["message"]


def test_llm_failure_returns_503_and_is_logged(
    tmp_path: Path, made: dict[str, FakePipeline]
) -> None:
    test_client, _ = make_client(tmp_path, made, fail=True)
    with test_client:
        response = test_client.post("/api/ask", json={"question": "Q?"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "llm_unavailable" and "boom" not in error["message"]
    assert read_jsonl(tmp_path / "logs" / "queries.jsonl")[0]["error"] == "llm_unavailable"


# --------------------------------------------------------------- rate limit


def test_rate_limit_per_ip(tmp_path: Path, made: dict[str, FakePipeline]) -> None:
    test_client, clock = make_client(tmp_path, made, rate_limit_per_minute=2)
    with test_client:
        assert test_client.post("/api/ask", json={"question": "1?"}).status_code == 200
        assert test_client.post("/api/ask", json={"question": "2?"}).status_code == 200
        blocked = test_client.post("/api/ask", json={"question": "3?"})
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
        assert int(blocked.headers["Retry-After"]) == 60
        clock.now += 61
        assert test_client.post("/api/ask", json={"question": "4?"}).status_code == 200
    assert len(made["hybrid_rerank"].questions) == 3  # the blocked one never ran


def test_forwarded_for_is_only_used_when_trusted(
    tmp_path: Path, made: dict[str, FakePipeline]
) -> None:
    for trusted, expected in [(False, 429), (True, 200)]:
        test_client, _ = make_client(
            tmp_path, made, rate_limit_per_minute=1, trust_forwarded_for=trusted
        )
        with test_client:
            test_client.post("/api/ask", json={"question": "1?"},
                             headers={"X-Forwarded-For": "1.1.1.1"})  # fmt: skip
            second = test_client.post(
                "/api/ask", json={"question": "2?"}, headers={"X-Forwarded-For": "2.2.2.2"}
            )
        assert second.status_code == expected


# ----------------------------------------------------------------- feedback


def test_feedback_is_logged(client: TestClient, tmp_path: Path) -> None:
    qid = client.post("/api/ask", json={"question": "Q?"}).json()["question_id"]
    response = client.post(
        "/api/feedback", json={"question_id": qid, "helpful": False, "comment": " too long "}
    )
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    record = read_jsonl(tmp_path / "logs" / "feedback.jsonl")[0]
    assert record["question_id"] == qid
    assert record["helpful"] is False
    assert record["comment"] == "too long"
    assert record["known_question"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"question_id": "not-an-id", "helpful": True},
        {"question_id": "a" * 32},
        {"question_id": "a" * 32, "helpful": "yes"},
        {"question_id": "a" * 32, "helpful": True, "comment": "x" * 1001},
    ],
)
def test_invalid_feedback_is_rejected(client: TestClient, payload: dict) -> None:
    response = client.post("/api/feedback", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


# ------------------------------------------------------------ sources/static


def test_sources_lists_each_document_once(client: TestClient) -> None:
    body = client.get("/api/sources").json()
    assert body["count"] == len(CORPUS)
    titles = [s["title"] for s in body["sources"]]
    assert titles == sorted(titles, key=str.lower)
    assert set(body["sources"][0]) == {"doc_id", "title", "url", "language"}


def test_list_sources_deduplicates_chunks_of_one_document() -> None:
    chunks = [dict(CORPUS[0]), {**CORPUS[0], "chunk_id": "anmeldung-0001"}]
    assert len(list_sources(ChunkStore(chunks))) == 1


def test_chat_page_is_served_at_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Signpost – Your guide to arriving at DIT" in response.text
    for asset in ("/app.js", "/style.css"):
        assert client.get(asset).status_code == 200


def test_unknown_api_path_returns_json_404(client: TestClient) -> None:
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_returns_json_error(client: TestClient) -> None:
    response = client.get("/api/ask")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


# ------------------------------------------------------------- daily limit


class Today:
    """A settable UTC "now" for the daily limit."""

    def __init__(self) -> None:
        self.value = datetime(2026, 11, 19, 23, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


def test_daily_limit_blocks_further_llm_questions(
    tmp_path: Path, made: dict[str, FakePipeline]
) -> None:
    today = Today()
    test_client, _ = make_client(tmp_path, made, now=today, daily_question_limit=2)
    with test_client:
        assert test_client.post("/api/ask", json={"question": "1?"}).status_code == 200
        assert test_client.post("/api/ask", json={"question": "2?"}).status_code == 200
        blocked = test_client.post("/api/ask", json={"question": "3?"})
        health = test_client.get("/api/health").json()

    assert blocked.status_code == 429
    error = blocked.json()["error"]
    assert error["code"] == "daily_limit_reached"
    assert "daily limit" in error["message"] and "00:00 UTC" in error["message"]
    assert blocked.headers["Retry-After"] == "3600"  # 23:00 -> midnight UTC
    assert made["hybrid_rerank"].questions == ["1?", "2?"]  # pipeline not called
    assert health["questions_today"] == 2
    logged = read_jsonl(tmp_path / "logs" / "queries.jsonl")
    assert logged[-1]["error"] == "daily_limit"


def test_questions_without_llm_call_do_not_count(
    tmp_path: Path, made: dict[str, FakePipeline]
) -> None:
    test_client, _ = make_client(tmp_path, made, daily_question_limit=1)
    with test_client:
        for _ in range(3):  # the fake refuses pizza questions without an LLM call
            refusal = test_client.post("/api/ask", json={"question": "Best pizza?"})
            assert refusal.status_code == 200
        assert test_client.get("/api/health").json()["questions_today"] == 0
        assert test_client.post("/api/ask", json={"question": "Fees?"}).status_code == 200
        assert test_client.post("/api/ask", json={"question": "More?"}).status_code == 429


def test_llm_failures_do_not_use_the_daily_budget(
    tmp_path: Path, made: dict[str, FakePipeline]
) -> None:
    test_client, _ = make_client(tmp_path, made, fail=True, daily_question_limit=1)
    with test_client:
        for _ in range(2):
            assert test_client.post("/api/ask", json={"question": "Q?"}).status_code == 503
        assert test_client.get("/api/health").json()["questions_today"] == 0


def test_daily_limit_resets_at_midnight_utc(tmp_path: Path, made: dict[str, FakePipeline]) -> None:
    today = Today()
    test_client, _ = make_client(tmp_path, made, now=today, daily_question_limit=1)
    with test_client:
        assert test_client.post("/api/ask", json={"question": "1?"}).status_code == 200
        assert test_client.post("/api/ask", json={"question": "2?"}).status_code == 429
        today.value = datetime(2026, 11, 20, 0, 0, 1, tzinfo=UTC)
        assert test_client.post("/api/ask", json={"question": "3?"}).status_code == 200


def test_daily_limit_zero_means_unlimited(tmp_path: Path, made: dict[str, FakePipeline]) -> None:
    test_client, _ = make_client(tmp_path, made, daily_question_limit=0, rate_limit_per_minute=100)
    with test_client:
        for i in range(25):
            assert test_client.post("/api/ask", json={"question": f"{i}?"}).status_code == 200
