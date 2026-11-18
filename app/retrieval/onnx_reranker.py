"""Cross-encoder reranker running an int8 ONNX export with ONNX Runtime.

Drop-in replacement for sentence-transformers' ``CrossEncoder.predict`` (same tokenizer,
sigmoid scores 0-1), about 1.5x faster on CPU. The model directory is created once by
``scripts/export_reranker.py`` and holds ``model.onnx``, the tokenizer files and
``export_info.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)

MODEL_FILE = "model.onnx"
INFO_FILE = "export_info.json"


class SessionLike(Protocol):
    """The subset of ``onnxruntime.InferenceSession`` used here (lets tests pass a fake)."""

    def get_inputs(self) -> list[Any]: ...

    def run(self, output_names: Any, input_feed: dict[str, np.ndarray]) -> list[np.ndarray]: ...


def sigmoid(logits: np.ndarray) -> np.ndarray:
    """Numerically stable logistic function."""
    logits = np.asarray(logits, dtype=np.float64)
    return np.exp(-np.logaddexp(0.0, -logits))


class OnnxCrossEncoder:
    """Scores (query, passage) pairs with an ONNX cross-encoder; returns probabilities 0-1."""

    def __init__(self, session: SessionLike, tokenizer: Any, max_length: int = 512) -> None:
        self.session = session
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.input_names = {i.name for i in session.get_inputs()}

    @classmethod
    def from_dir(
        cls,
        model_dir: Path,
        expected_model: str | None = None,
        threads: int = 0,
        max_length: int = 512,
    ) -> OnnxCrossEncoder:
        """Load ``model_dir`` written by ``scripts/export_reranker.py``.

        ``expected_model`` (the Hugging Face id from RERANKER_MODEL) must match the model the
        export was made from; ``threads`` = 0 lets ONNX Runtime choose; ``max_length`` is the
        token limit per (query, passage) pair.
        """
        model_dir = Path(model_dir)
        model_path = model_dir / MODEL_FILE
        if not model_path.exists():
            raise FileNotFoundError(
                f"no ONNX reranker at {model_path}; run `python scripts/export_reranker.py` "
                "(one-time, needs `pip install -e .[export]`) or set RERANKER_BACKEND=torch"
            )
        info_path = model_dir / INFO_FILE
        if info_path.exists():
            source = json.loads(info_path.read_text(encoding="utf-8")).get("source_model")
            if expected_model and source != expected_model:
                raise ValueError(
                    f"{model_dir} was exported from {source!r}, but RERANKER_MODEL is "
                    f"{expected_model!r}; re-run `python scripts/export_reranker.py --force`"
                )
        else:
            logger.warning("%s has no %s; cannot verify the source model", model_dir, INFO_FILE)

        import onnxruntime as ort
        from transformers import AutoTokenizer

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if threads > 0:
            options.intra_op_num_threads = threads
        logger.info("loading ONNX reranker %s", model_path)
        session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        return cls(session, AutoTokenizer.from_pretrained(model_dir), max_length=max_length)

    def predict(
        self, sentences: list[tuple[str, str]], batch_size: int = 16, **kwargs: Any
    ) -> np.ndarray:
        """Return one 0-1 relevance score per (query, passage) pair.

        Extra keyword arguments of ``CrossEncoder.predict`` (e.g. ``show_progress_bar``) are
        accepted and ignored.
        """
        scores: list[np.ndarray] = []
        for start in range(0, len(sentences), batch_size):
            batch = sentences[start : start + batch_size]
            encoded = self.tokenizer(
                [query for query, _ in batch],
                [passage for _, passage in batch],
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="np",
            )
            feeds = {
                name: np.asarray(value, dtype=np.int64)
                for name, value in encoded.items()
                if name in self.input_names
            }
            logits = self.session.run(None, feeds)[0]
            scores.append(sigmoid(np.asarray(logits).reshape(-1)))
        return np.concatenate(scores) if scores else np.zeros(0, dtype=np.float64)
