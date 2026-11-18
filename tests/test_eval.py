"""Tests for the evaluation runner's automatic scoring (no models, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.run_eval import load_questions, score


def test_score_retrieval_and_citations() -> None:
    result = score(["D14", "D15"], ["D08", "D14", "D08"], ["D14", "D08"])
    assert result == {
        "retrieval_hit": True,
        "retrieval_all": False,
        "first_rank": 2,
        "citation_hit": True,
        "citation_precision": 0.5,
    }


def test_score_without_expected_sources_is_not_scored() -> None:
    result = score([], ["D11"], [])
    assert result["retrieval_hit"] is None and result["citation_precision"] is None


def test_score_without_citations() -> None:
    result = score(["D01"], ["D01"], [])
    assert result["retrieval_all"] is True and result["citation_hit"] is None


def test_load_questions_validates_fields(tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"questions": [{"id": "Q1", "question": "?"}]}))
    with pytest.raises(ValueError):
        load_questions(path)
    path.write_text(
        json.dumps({"questions": [{"id": "Q1", "question": "?", "expected_source_ids": []}]})
    )
    assert load_questions(path)[0]["id"] == "Q1"
