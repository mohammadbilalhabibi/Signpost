"""Application settings, loaded from environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Typed configuration for Degbot. Env var names are the upper-case field names."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM (any OpenAI-compatible endpoint)
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr = SecretStr("")
    llm_api_version: str = Field(
        default="2024-10-21", description="Azure OpenAI only: the REST API version."
    )
    llm_timeout: float = Field(default=30.0, gt=0, description="Seconds per LLM request.")
    llm_max_retries: int = Field(
        default=1, ge=0, description="Retries on timeouts, connection errors, 429 and 5xx."
    )
    llm_max_output_tokens: int = Field(default=600, ge=16, description="Answer length limit.")
    llm_temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature; unset = provider default (some models reject it).",
    )
    llm_token_param: Literal["auto", "max_tokens", "max_completion_tokens"] = Field(
        default="auto",
        description=(
            "Name of the output-limit parameter. auto: max_completion_tokens for openai/azure, "
            "max_tokens for other providers."
        ),
    )

    # Models
    embedding_model: str = "intfloat/multilingual-e5-base"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_backend: Literal["onnx", "torch"] = Field(
        default="onnx",
        description=(
            "onnx: int8 ONNX export of RERANKER_MODEL (scripts/export_reranker.py), ~1.5x "
            "faster on CPU; torch: the original fp32 model via sentence-transformers."
        ),
    )
    reranker_onnx_dir: Path = PROJECT_ROOT / "models" / "bge-reranker-v2-m3-onnx-int8"
    reranker_threads: int = Field(
        default=0, ge=0, description="ONNX Runtime intra-op threads; 0 = runtime default."
    )

    # Data & index locations (relative paths are resolved against the project root)
    chunks_path: Path = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
    index_dir: Path = PROJECT_ROOT / "index"

    # Retrieval
    top_k_retrieve: int = Field(default=20, ge=1, description="Candidates per retriever.")
    rerank_candidates: int = Field(
        default=10,
        ge=1,
        description="Hybrid candidates scored by the reranker (main latency knob).",
    )
    rerank_max_length: int = Field(
        default=512,
        ge=32,
        le=8192,
        description="Max tokens per (question, passage) pair fed to the reranker.",
    )
    top_k_final: int = Field(default=5, ge=1, description="Passages passed to the LLM.")
    rrf_k: int = Field(default=60, ge=1, description="Reciprocal Rank Fusion constant.")
    refusal_threshold: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum reranker score (0-1) of the best passage; below it the assistant "
            "refuses without calling the LLM. Provisional: chosen between an off-topic "
            "question (0.0003) and the lowest answerable one (0.23) with the int8 reranker; "
            "to be tuned on the evaluation set."
        ),
    )

    # Web API
    logs_dir: Path = PROJECT_ROOT / "logs"
    rate_limit_per_minute: int = Field(
        default=10, ge=1, description="Questions per client IP per minute (POST /api/ask)."
    )
    feedback_rate_limit_per_minute: int = Field(
        default=30, ge=1, description="Feedback requests per client IP per minute."
    )
    trust_forwarded_for: bool = Field(
        default=False,
        description=(
            "Use the first X-Forwarded-For address as client IP (only behind a trusted "
            "reverse proxy, e.g. Hugging Face Spaces)."
        ),
    )

    # Ingestion
    ingest_user_agent: str = (
        "DegbotIngest/0.1 (non-commercial student project; bilingual RAG assistant)"
    )
    ingest_request_delay: float = Field(
        default=1.0, ge=1.0, description="Minimum seconds between requests to one host."
    )
    ingest_timeout: float = Field(default=30.0, gt=0, description="HTTP timeout in seconds.")
    chunk_tokens: int = Field(
        default=350, ge=50, le=512, description="Maximum tokens per chunk (incl. prefix)."
    )
    chunk_overlap: float = Field(
        default=0.15, ge=0.0, lt=0.5, description="Overlap between chunks, share of size."
    )
    chunk_min_section_tokens: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Sibling sections smaller than this are merged into one chunk. "
            "Default: CHUNK_TOKENS // 4; 0 disables merging."
        ),
    )

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        for name in ("chunks_path", "index_dir", "reranker_onnx_dir", "logs_dir"):
            path = getattr(self, name)
            if not path.is_absolute():
                object.__setattr__(self, name, PROJECT_ROOT / path)
        return self

    @model_validator(mode="after")
    def _check_top_k(self) -> "Settings":
        if self.top_k_final > self.top_k_retrieve:
            raise ValueError("TOP_K_FINAL must not be larger than TOP_K_RETRIEVE")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (created once)."""
    return Settings()
