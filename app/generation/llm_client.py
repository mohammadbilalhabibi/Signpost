"""One OpenAI-compatible chat client for all providers (OpenAI, Azure, Mistral, Ollama, ...).

Provider, base URL, model and key come from the settings. Timeouts and retries are handled
by the ``openai`` SDK (``LLM_TIMEOUT``, ``LLM_MAX_RETRIES`` = 1 by default: connection errors,
timeouts, 429 and 5xx are retried once with backoff).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import openai

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Providers whose current models expect ``max_completion_tokens`` instead of ``max_tokens``.
_COMPLETION_TOKENS_PROVIDERS = {"openai", "azure"}
_PLACEHOLDER_KEY = "not-needed"  # the SDK refuses an empty key; Ollama ignores it


class GenerationError(RuntimeError):
    """The LLM request failed (after the retry) or returned no text."""


@dataclass(frozen=True)
class LLMResult:
    """Text and metadata of one chat completion."""

    text: str
    model: str
    finish_reason: str | None
    usage: dict[str, int] = field(default_factory=dict)


class LLMClient:
    """Thin wrapper around the OpenAI SDK; create it once and reuse it for every question."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.provider = settings.llm_provider.strip().lower()
        self.model = settings.llm_model
        self._key = settings.llm_api_key.get_secret_value()
        self.client = client if client is not None else self._make_client()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> LLMClient:
        """Build a client from the given (or the process-wide) settings."""
        return cls(settings or get_settings())

    def _make_client(self) -> openai.OpenAI:
        common = {
            "api_key": self._key or _PLACEHOLDER_KEY,
            "timeout": self.settings.llm_timeout,
            "max_retries": self.settings.llm_max_retries,
        }
        if self.provider == "azure":
            # LLM_BASE_URL = https://<resource>.openai.azure.com, LLM_MODEL = deployment name
            return openai.AzureOpenAI(
                azure_endpoint=self.settings.llm_base_url,
                api_version=self.settings.llm_api_version,
                **common,
            )
        return openai.OpenAI(base_url=self.settings.llm_base_url, **common)

    @property
    def token_param(self) -> str:
        """Name of the output-length parameter sent to this provider."""
        if self.settings.llm_token_param != "auto":
            return self.settings.llm_token_param
        if self.provider in _COMPLETION_TOKENS_PROVIDERS:
            return "max_completion_tokens"
        return "max_tokens"

    def request_kwargs(self, system: str, user: str) -> dict[str, Any]:
        """Arguments for ``chat.completions.create`` (exposed for tests)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            self.token_param: self.settings.llm_max_output_tokens,
        }
        if self.settings.llm_temperature is not None:
            kwargs["temperature"] = self.settings.llm_temperature
        return kwargs

    def complete(self, system: str, user: str) -> LLMResult:
        """Send one chat request and return the reply text; raise GenerationError on failure."""
        try:
            response = self.client.chat.completions.create(**self.request_kwargs(system, user))
        except openai.OpenAIError as exc:
            raise GenerationError(self._redact(f"LLM request failed: {exc}")) from None
        choice = response.choices[0] if response.choices else None
        text = (choice.message.content or "").strip() if choice else ""
        finish = choice.finish_reason if choice else None
        if not text:
            hint = " (raise LLM_MAX_OUTPUT_TOKENS)" if finish == "length" else ""
            raise GenerationError(f"LLM returned no text, finish_reason={finish}{hint}")
        usage = {}
        if getattr(response, "usage", None) is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
        return LLMResult(text=text, model=response.model, finish_reason=finish, usage=usage)

    def _redact(self, message: str) -> str:
        return message.replace(self._key, "[REDACTED]") if self._key else message
