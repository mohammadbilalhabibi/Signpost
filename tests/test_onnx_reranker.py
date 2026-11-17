"""Tests for the ONNX int8 reranker and the reranker backend selection.

The default tests use a fake ONNX session and tokenizer (no model files needed). The test
marked ``slow`` compares the real int8 export with the original PyTorch model; it is skipped
if ``scripts/export_reranker.py`` has not been run.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings
from app.retrieval import factory
from app.retrieval.bm25 import tokenize
from app.retrieval.onnx_reranker import INFO_FILE, MODEL_FILE, OnnxCrossEncoder, sigmoid
from tests.test_retrieval import CORPUS, QUESTIONS, make_retrievers

# ------------------------------------------------------------------- fake ONNX


class FakeTokenizer:
    """Encodes each pair as [number of query tokens found in the passage, 1, 1]."""

    def __call__(self, queries, passages, **kwargs) -> dict[str, np.ndarray]:
        overlap = [
            len(set(tokenize(q)) & set(tokenize(p))) for q, p in zip(queries, passages, strict=True)
        ]
        ids = np.array([[n, 1, 1] for n in overlap], dtype=np.int32)
        return {
            "input_ids": ids,
            "attention_mask": np.ones_like(ids),
            "token_type_ids": np.zeros_like(ids),  # not a model input -> must be dropped
        }


class FakeSession:
    """Logit = overlap count - 1, shaped (batch, 1) like the real export."""

    def __init__(self) -> None:
        self.feeds: list[dict[str, np.ndarray]] = []

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")]

    def run(self, output_names, input_feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.feeds.append(input_feed)
        logits = input_feed["input_ids"][:, :1].astype(np.float32) - 1.0
        return [logits]


def fake_encoder() -> tuple[OnnxCrossEncoder, FakeSession]:
    session = FakeSession()
    return OnnxCrossEncoder(session, FakeTokenizer()), session


# ---------------------------------------------------------------------- predict


def test_predict_batches_and_returns_sigmoid_scores() -> None:
    encoder, session = fake_encoder()
    pairs = [("semester fee", "the semester fee is 82 euro")] + [("visa", "mensa menu")] * 4
    scores = encoder.predict(pairs, batch_size=2, show_progress_bar=False)

    assert len(session.feeds) == 3  # 5 pairs in batches of 2
    assert scores.shape == (5,)
    assert scores[0] == pytest.approx(float(sigmoid(np.array(1.0))))  # 2 shared tokens
    assert scores[1] == pytest.approx(float(sigmoid(np.array(-1.0))))
    for feed in session.feeds:
        assert set(feed) == {"input_ids", "attention_mask"}
        assert all(v.dtype == np.int64 for v in feed.values())


def test_predict_without_pairs_returns_empty_array() -> None:
    encoder, session = fake_encoder()
    assert encoder.predict([]).shape == (0,)
    assert session.feeds == []


def test_sigmoid_is_stable_for_large_logits() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        probs = sigmoid(np.array([-1000.0, 0.0, 1000.0]))
    assert probs.tolist() == pytest.approx([0.0, 0.5, 1.0])


def test_onnx_encoder_works_inside_reranked_retriever() -> None:
    encoder, _ = fake_encoder()
    reranked = make_retrievers(CORPUS, cross_encoder=encoder)["hybrid_rerank"]
    hits = reranked.search("Wie hoch ist der Semesterbeitrag?", k=3)
    assert hits[0].chunk_id == "fees-0000"
    assert all(0.0 <= h.score <= 1.0 for h in hits)


# ---------------------------------------------------------------------- loading


def test_missing_export_tells_how_to_create_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="export_reranker.py"):
        OnnxCrossEncoder.from_dir(tmp_path / "nothing-here")


def test_export_of_another_model_is_rejected(tmp_path: Path) -> None:
    (tmp_path / MODEL_FILE).write_bytes(b"")
    (tmp_path / INFO_FILE).write_text(json.dumps({"source_model": "other/model"}))
    with pytest.raises(ValueError, match="other/model"):
        OnnxCrossEncoder.from_dir(tmp_path, expected_model="BAAI/bge-reranker-v2-m3")


# --------------------------------------------------------------------- settings


def test_reranker_settings_defaults_and_path_resolution() -> None:
    settings = Settings(_env_file=None)
    assert settings.reranker_backend == "onnx"
    assert settings.top_k_rerank == 10
    relative = Settings(_env_file=None, reranker_onnx_dir="models/custom")
    assert relative.reranker_onnx_dir == PROJECT_ROOT / "models" / "custom"


def test_unknown_reranker_backend_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reranker_backend="tensorflow")


@pytest.mark.parametrize(("backend", "expected"), [("onnx", "onnx"), ("torch", "torch")])
def test_backend_setting_selects_loader(
    monkeypatch: pytest.MonkeyPatch, backend: str, expected: str
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(factory, "load_reranker", lambda *a: calls.append(("torch", *a)))
    monkeypatch.setattr(factory, "load_onnx_reranker", lambda *a: calls.append(("onnx", *a)))
    settings = Settings(_env_file=None, reranker_backend=backend, reranker_threads=3)

    factory.reranker_from_settings(settings)

    assert calls[0][0] == expected
    if expected == "onnx":
        assert calls[0][1:] == (settings.reranker_onnx_dir, settings.reranker_model, 3)


# ------------------------------------------------------------- real model (slow)


@pytest.mark.slow
def test_int8_export_matches_pytorch_reranker() -> None:
    settings = Settings()
    if not (settings.reranker_onnx_dir / MODEL_FILE).exists():
        pytest.skip("no ONNX export; run python scripts/export_reranker.py")
    onnx = factory.load_onnx_reranker(settings.reranker_onnx_dir, settings.reranker_model)
    torch = factory.load_reranker(settings.reranker_model)

    texts = [c["text"] for c in CORPUS]
    for question, expected in QUESTIONS:
        pairs = [(question, t) for t in texts]
        int8 = onnx.predict(pairs)
        fp32 = np.asarray(torch.predict(pairs, show_progress_bar=False))
        assert CORPUS[int(np.argmax(int8))]["chunk_id"] == expected
        assert int(np.argmax(int8)) == int(np.argmax(fp32))
        assert np.abs(int8 - fp32).max() < 0.15, question  # measured max on 100 pairs: 0.11
