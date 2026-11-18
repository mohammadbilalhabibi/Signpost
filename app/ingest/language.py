"""Language detection restricted to the two languages Signpost supports."""

from __future__ import annotations

import logging

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0  # langdetect is random by default; make results reproducible

logger = logging.getLogger(__name__)

SUPPORTED = ("de", "en")


def detect_language(text: str, sample_chars: int = 5000) -> str:
    """Return ``"de"`` or ``"en"`` (whichever is more likely), or ``"unknown"``.

    Only the first ``sample_chars`` characters are used; that is plenty for
    langdetect and keeps it fast on long PDFs.
    """
    sample = text[:sample_chars].strip()
    if len(sample) < 20:
        return "unknown"
    try:
        candidates = detect_langs(sample)
    except LangDetectException:
        return "unknown"
    probs = {c.lang: c.prob for c in candidates}
    best = max(SUPPORTED, key=lambda lang: probs.get(lang, 0.0))
    if probs.get(best, 0.0) < 0.2:
        logger.warning("language is neither de nor en (detected %s)", candidates[0].lang)
        return "unknown"
    return best
