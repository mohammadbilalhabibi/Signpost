---
license: apache-2.0
base_model: BAAI/bge-reranker-v2-m3
library_name: onnx
pipeline_tag: text-classification
tags:
  - reranker
  - cross-encoder
  - onnx
  - int8
---

# bge-reranker-v2-m3, ONNX int8 (dynamic quantization)

An int8 ONNX export of [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)
(Apache-2.0), used by [Signpost](https://github.com/mohammadbilalhabibi/Signpost) to rerank
retrieved passages on CPU.

- Made with `scripts/export_reranker.py`: TorchScript ONNX export (opset 17), then
  ONNX Runtime dynamic quantization (QInt8 weights). Versions and settings are in
  `export_info.json`.
- Files: `model.onnx` (~570 MB), the original tokenizer (`tokenizer.json`,
  `tokenizer_config.json`), `export_info.json`.
- Output: one logit per (query, passage) pair; apply a sigmoid for a 0-1 relevance score.
- Measured against the PyTorch fp32 model on 100 query-passage pairs: mean absolute score
  difference 0.015 (max 0.11), same best passage for 10/10 queries; about 1.5x faster on a
  4-core laptop CPU.

All credit for the model goes to BAAI; this repository only contains a quantized export.
