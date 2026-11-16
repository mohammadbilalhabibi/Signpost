"""Smoke tests: the package imports, settings load, and the API starts."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import app
from app.config import Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("TOP_K_RETRIEVE", "TOP_K_FINAL", "EMBEDDING_MODEL"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.top_k_retrieve == 20
    assert settings.top_k_final == 5
    assert settings.embedding_model == "intfloat/multilingual-e5-base"


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "test-model"
    assert settings.llm_api_key.get_secret_value() == "dummy"
    assert "dummy" not in repr(settings)


def test_settings_reject_inconsistent_top_k() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, top_k_retrieve=3, top_k_final=5)


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
