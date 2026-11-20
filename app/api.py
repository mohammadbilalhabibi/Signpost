"""FastAPI app: chat API (/api/...) plus the static chat page at /.

The retriever, reranker and LLM client are loaded once at startup (lifespan) and reused by
every request. Run with:  python -m uvicorn app.api:app --port 7860
"""

from __future__ import annotations

import ipaddress
import json
import logging
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.generation.llm_client import GenerationError
from app.generation.pipeline import Answer
from app.ratelimit import DailyLimiter, RateLimiter
from app.retrieval.base import ChunkStore
from app.retrieval.factory import Mode

logger = logging.getLogger("signpost.api")

STATIC_DIR = Path(__file__).parent / "static"
MAX_QUESTION_CHARS = 500
MAX_COMMENT_CHARS = 1000
DEFAULT_MODE: Mode = "hybrid_rerank"
DAILY_LIMIT_MESSAGE = (
    "Signpost has reached its daily limit of answered questions. Please try again tomorrow "
    "(the limit resets at 00:00 UTC)."
)


class DailyLimitReached(Exception):
    """The shared daily question budget (DAILY_QUESTION_LIMIT) is used up."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("daily question limit reached")
        self.retry_after = retry_after


# ----------------------------------------------------------------- request bodies


class AskRequest(BaseModel):
    """POST /api/ask body."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS)
    ]
    mode: Mode | None = None


class FeedbackRequest(BaseModel):
    """POST /api/feedback body."""

    model_config = ConfigDict(extra="forbid")

    question_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
    helpful: StrictBool
    comment: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_COMMENT_CHARS)]
        | None
    ) = None


# ----------------------------------------------------------------------- services


class PipelineLike(Protocol):
    """What the API needs from AnswerPipeline (lets tests pass a fake)."""

    def answer(self, question: str) -> Answer: ...


@dataclass
class Services:
    """Everything loaded once at startup and shared by all requests."""

    store: ChunkStore
    make_pipeline: Callable[[str], PipelineLike]
    models: dict[str, str]
    default_mode: str = DEFAULT_MODE
    _pipelines: dict[str, PipelineLike] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def pipeline(self, mode: str) -> PipelineLike:
        """Pipeline for ``mode``; the default mode is built at startup, others on first use."""
        with self._lock:
            if mode not in self._pipelines:
                self._pipelines[mode] = self.make_pipeline(mode)
            return self._pipelines[mode]

    @property
    def loaded_modes(self) -> list[str]:
        """Modes whose pipeline is already built."""
        return sorted(self._pipelines)


def load_services(settings: Settings) -> Services:
    """Load chunks, retriever models and the LLM client (slow: ~20-40 s on CPU)."""
    from app.generation.llm_client import LLMClient
    from app.generation.pipeline import AnswerPipeline
    from app.retrieval.factory import get_retriever, load_store

    llm = LLMClient.from_settings(settings)

    def make_pipeline(mode: str) -> PipelineLike:
        return AnswerPipeline(get_retriever(mode, settings), llm, settings, mode)

    models = {
        "embedding": settings.embedding_model,
        "reranker": f"{settings.reranker_model} ({settings.reranker_backend})",
        "llm": f"{settings.llm_provider}/{settings.llm_model}",
    }
    return Services(load_store(Path(settings.chunks_path)), make_pipeline, models)


def list_sources(store: ChunkStore) -> list[dict[str, str]]:
    """One entry per source document in the index, sorted by title."""
    docs: dict[str, dict[str, str]] = {}
    for chunk in store.chunks:
        docs.setdefault(
            chunk["doc_id"],
            {
                "doc_id": chunk["doc_id"],
                "title": chunk["title"],
                "url": chunk["url"],
                "language": chunk["language"],
            },
        )
    return sorted(docs.values(), key=lambda d: d["title"].lower())


class JsonlLog:
    """Thread-safe append-only JSON Lines file; write errors are logged, never raised."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: dict[str, Any]) -> None:
        """Append one record as a JSON line."""
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("could not write %s: %s", self.path, exc)


def client_address(peer: str | None, forwarded_for: str | None, trust_forwarded: bool) -> str:
    """Client IP used as the rate-limit key.

    Behind a trusted reverse proxy (``TRUST_FORWARDED_FOR``) the real client is the
    right-most *public* address in X-Forwarded-For: proxies append the address they saw, so
    entries further left can be set by the client itself (spoofing), and private addresses
    on the right are internal proxy hops. Otherwise the socket peer address is used.
    """
    if trust_forwarded and forwarded_for:
        for part in reversed(forwarded_for.split(",")):
            candidate = part.strip().strip("[]")
            if candidate.count(":") == 1:  # IPv4 with a port, e.g. "203.0.113.7:51234"
                candidate = candidate.split(":")[0]
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.is_global:
                return str(address)
    return peer or "unknown"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    headers = extra.pop("headers", None)
    return JSONResponse(
        {"error": {"code": code, "message": message, **extra}}, status_code=status, headers=headers
    )


_STATUS_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    429: "rate_limited",
    503: "unavailable",
}


# ---------------------------------------------------------------------------- app


def create_app(
    settings: Settings | None = None,
    loader: Callable[[Settings], Services] = load_services,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    """Build the FastAPI app; ``loader``, ``clock`` and ``now`` are replaceable for tests."""
    settings = settings or get_settings()
    ask_limiter = RateLimiter(settings.rate_limit_per_minute, clock=clock)
    feedback_limiter = RateLimiter(settings.feedback_rate_limit_per_minute, clock=clock)
    daily_limiter = DailyLimiter(settings.daily_question_limit, now=now)
    query_log = JsonlLog(Path(settings.logs_dir) / "queries.jsonl")
    feedback_log = JsonlLog(Path(settings.logs_dir) / "feedback.jsonl")
    recent_ids: deque[str] = deque(maxlen=10_000)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        start = time.perf_counter()
        services = await run_in_threadpool(loader, settings)
        await run_in_threadpool(services.pipeline, services.default_mode)
        app.state.services = services
        logger.info("models loaded in %.1f s", time.perf_counter() - start)
        yield

    app = FastAPI(title="Signpost", version="0.2.0", lifespan=lifespan)

    # ------------------------------------------------------------- helpers

    def services_of(request: Request) -> Services:
        services = getattr(request.app.state, "services", None)
        if services is None:
            raise HTTPException(503, "The models are still loading. Please try again shortly.")
        return services

    def client_ip(request: Request) -> str:
        peer = request.client.host if request.client else None
        return client_address(
            peer, request.headers.get("x-forwarded-for"), settings.trust_forwarded_for
        )

    def enforce(limiter: RateLimiter, request: Request) -> None:
        retry_after = limiter.hit(client_ip(request))
        if retry_after is not None:
            raise HTTPException(
                429,
                f"Too many requests. Please wait {retry_after} s and try again.",
                headers={"Retry-After": str(retry_after)},
            )

    # ------------------------------------------------------------- errors

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p != "body"]
            if err.get("type") == "json_invalid":
                details.append({"field": "body", "message": "Request body is not valid JSON."})
            else:
                details.append({"field": ".".join(loc) or "body", "message": err.get("msg", "")})
        message = "; ".join(f"{d['field']}: {d['message']}" for d in details)
        return _error(422, "invalid_request", message or "Invalid request.", details=details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        return _error(exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(DailyLimitReached)
    async def daily_limit_reached(request: Request, exc: DailyLimitReached) -> JSONResponse:
        return _error(
            429,
            "daily_limit_reached",
            DAILY_LIMIT_MESSAGE,
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(GenerationError)
    async def generation_error(request: Request, exc: GenerationError) -> JSONResponse:
        logger.error("LLM error: %s", exc)
        return _error(
            503,
            "llm_unavailable",
            "The language model is not reachable right now. Please try again in a minute.",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path)
        return _error(500, "internal_error", "Something went wrong on our side.")

    # ------------------------------------------------------------- routes

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness probe (does not need the models)."""
        return {"status": "ok"}

    @app.get("/api/health")
    def api_health(request: Request) -> dict[str, Any]:
        """Status, number of chunks/documents and the loaded models."""
        services = services_of(request)
        return {
            "status": "ok",
            "chunks": len(services.store),
            "documents": len(list_sources(services.store)),
            "models_loaded": True,
            "models": services.models,
            "default_mode": services.default_mode,
            "modes_loaded": services.loaded_modes,
            "questions_today": daily_limiter.used,
            "daily_question_limit": settings.daily_question_limit,
        }

    @app.get("/api/sources")
    def sources(request: Request) -> dict[str, Any]:
        """All source documents in the index (title, url, language)."""
        docs = list_sources(services_of(request).store)
        return {"count": len(docs), "sources": docs}

    @app.post("/api/ask")
    def ask(body: AskRequest, request: Request) -> dict[str, Any]:
        """Answer a question from the sources; the result carries a question_id."""
        enforce(ask_limiter, request)
        services = services_of(request)
        mode = body.mode or services.default_mode
        question_id = uuid.uuid4().hex
        record: dict[str, Any] = {"id": question_id, "timestamp": _now(), "mode": mode}
        if not daily_limiter.acquire():
            query_log.append({**record, "question": body.question, "error": "daily_limit"})
            raise DailyLimitReached(daily_limiter.seconds_until_reset())
        try:
            result = services.pipeline(mode).answer(body.question)
        except GenerationError:
            daily_limiter.release()
            query_log.append({**record, "question": body.question, "error": "llm_unavailable"})
            raise
        except Exception:
            daily_limiter.release()
            raise
        if result.model is None:  # small talk or score-threshold refusal: no LLM call
            daily_limiter.release()
        recent_ids.append(question_id)
        query_log.append(
            {
                **record,
                "question": result.question,
                "language": result.language,
                "refused": result.refused,
                "refusal_reason": result.refusal_reason,
                "best_score": result.best_score,
                "cited_doc_ids": sorted({c.doc_id for c in result.citations}),
                "timings_ms": result.timings_ms,
            }
        )
        return {"question_id": question_id, **result.to_dict()}

    @app.post("/api/feedback")
    def feedback(body: FeedbackRequest, request: Request) -> dict[str, str]:
        """Store a thumbs up/down (and optional comment) for an answer."""
        enforce(feedback_limiter, request)
        feedback_log.append(
            {
                "question_id": body.question_id,
                "timestamp": _now(),
                "helpful": body.helpful,
                "comment": body.comment or None,
                "known_question": body.question_id in recent_ids,
            }
        )
        return {"status": "ok"}

    allowed_methods = {"ask": "POST", "feedback": "POST", "health": "GET", "sources": "GET"}

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_not_found(path: str, request: Request) -> None:
        """JSON 405 for a known endpoint with the wrong method, JSON 404 for unknown paths."""
        allowed = allowed_methods.get(path.strip("/"))
        if allowed:
            raise HTTPException(
                405,
                f"Use {allowed} for /api/{path.strip('/')}, not {request.method}.",
                headers={"Allow": allowed},
            )
        raise HTTPException(404, f"Unknown API endpoint: /api/{path}")

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
