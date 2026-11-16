"""Tiny helpers to read and write JSON Lines files (UTF-8, one object per line)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    """Write records to ``path`` (overwriting it) and return how many were written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> Iterator[dict]:
    """Yield the records of a JSON Lines file, skipping blank lines."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)
