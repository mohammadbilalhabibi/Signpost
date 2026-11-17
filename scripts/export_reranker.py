"""Export the reranker (RERANKER_MODEL) to ONNX and quantize it to int8 - a one-time step.

Writes model.onnx (int8, ~570 MB), the tokenizer files and export_info.json to
RERANKER_ONNX_DIR (default models/bge-reranker-v2-m3-onnx-int8/). The temporary fp32 export
(~2.2 GB) is deleted afterwards. Takes a few minutes on CPU and needs the export extras:

    pip install -e ".[export]"
    python scripts/export_reranker.py            # skip if the export already exists
    python scripts/export_reranker.py --force    # re-export
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.retrieval.onnx_reranker import INFO_FILE, MODEL_FILE, OnnxCrossEncoder, sigmoid

OPSET = 17
CHECK_PAIRS = [
    ("How do I register my address in Deggendorf?", "Anmeldung: register at the Bürgerbüro."),
    ("Wie hoch ist der Semesterbeitrag?", "Der Semesterbeitrag beträgt 72 Euro."),
    ("Can I work as a student?", "Die Mensa öffnet um 11 Uhr."),
    ("Krankenversicherung für Studierende", "Students must have health insurance."),
]


def export(model_name: str, out_dir: Path) -> dict:
    """Export ``model_name`` to int8 ONNX in ``out_dir``; return the export info written."""
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).eval()
    queries, passages = zip(*CHECK_PAIRS, strict=True)
    sample = tokenizer(
        list(queries), list(passages), padding=True, truncation=True, return_tensors="pt"
    )
    with torch.no_grad():
        reference = sigmoid(model(**sample).logits.reshape(-1).numpy())

    out_dir.mkdir(parents=True, exist_ok=True)
    timings = {}
    with tempfile.TemporaryDirectory(
        dir=out_dir.parent, prefix=".reranker-export-", ignore_cleanup_errors=True
    ) as tmp:
        fp32_path = Path(tmp) / "model_fp32.onnx"
        t0 = time.perf_counter()
        with torch.no_grad():
            # TorchScript exporter: its output matched PyTorch exactly in our benchmark.
            torch.onnx.export(
                model,
                (sample["input_ids"], sample["attention_mask"]),
                str(fp32_path),
                input_names=["input_ids", "attention_mask"],
                output_names=["logits"],
                dynamic_axes={
                    "input_ids": {0: "batch", 1: "seq"},
                    "attention_mask": {0: "batch", 1: "seq"},
                    "logits": {0: "batch"},
                },
                opset_version=OPSET,
                dynamo=False,
            )
        timings["export"] = round(time.perf_counter() - t0, 1)
        del model
        gc.collect()

        t0 = time.perf_counter()
        quantize_dynamic(str(fp32_path), str(out_dir / MODEL_FILE), weight_type=QuantType.QInt8)
        timings["quantize"] = round(time.perf_counter() - t0, 1)
    tokenizer.save_pretrained(out_dir)

    info_path = out_dir / INFO_FILE
    info = {
        "source_model": model_name,
        "quantization": "onnxruntime dynamic int8 (QInt8 weights)",
        "opset": OPSET,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "versions": {p: version(p) for p in ("torch", "transformers", "onnxruntime", "onnx")},
        "seconds": timings,
    }
    info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")

    scores = OnnxCrossEncoder.from_dir(out_dir, expected_model=model_name).predict(CHECK_PAIRS)
    info["check_max_score_diff_vs_pytorch"] = round(float(np.abs(scores - reference).max()), 4)
    info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--model", default=settings.reranker_model)
    parser.add_argument("--out", type=Path, default=settings.reranker_onnx_dir)
    parser.add_argument("--force", action="store_true", help="re-export an existing model")
    args = parser.parse_args(argv)

    if (args.out / MODEL_FILE).exists() and not args.force:
        print(f"{args.out / MODEL_FILE} already exists (use --force to re-export)")
        return 0
    print(f"exporting {args.model} -> {args.out} (takes a few minutes)")
    info = export(args.model, args.out)
    size_mb = (args.out / MODEL_FILE).stat().st_size / 1e6
    print(
        f"done: {MODEL_FILE} {size_mb:.0f} MB, export {info['seconds']['export']} s, "
        f"quantize {info['seconds']['quantize']} s, max score difference vs PyTorch on "
        f"{len(CHECK_PAIRS)} check pairs: {info['check_max_score_diff_vs_pytorch']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
