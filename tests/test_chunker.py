"""Unit tests for app.ingest.chunker (offline: uses a whitespace token counter)."""

import re

import pytest

from app.ingest.chunker import (
    Chunker,
    split_sections,
    split_sentences,
    whitespace_token_counter,
)

count = whitespace_token_counter


def make_sentences(n: int, words: int = 12, tag: str = "S") -> list[str]:
    """n distinct sentences of exactly ``words`` words each, e.g. 'S3 w w w ... end.'"""
    return [f"{tag}{i} " + " ".join(["wort"] * (words - 2)) + " ende." for i in range(n)]


def make_doc(text: str, **overrides: str) -> dict:
    doc = {
        "doc_id": "doc-1",
        "title": "Test Doc",
        "url": "https://example.org/a",
        "language": "de",
        "text": text,
    }
    doc.update(overrides)
    return doc


def body(chunk_text: str) -> str:
    """Chunk text without the 'title > section' prefix."""
    return chunk_text.split("\n\n", 1)[1]


@pytest.fixture
def long_doc() -> dict:
    para1 = " ".join(make_sentences(40, tag="A"))
    para2 = " ".join(make_sentences(25, tag="B"))
    return make_doc(f"## Wohnen\n\n{para1}\n\n## Versicherung\n\n{para2}")


# ------------------------------------------------------------------ sentences


def test_split_sentences_basic() -> None:
    assert split_sentences("Das ist eins. Das ist zwei! Ist das drei? Ja.") == [
        "Das ist eins.",
        "Das ist zwei!",
        "Ist das drei?",
        "Ja.",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Bring Dokumente mit, z. B. Pass und Visum.",
        "Bring documents, e.g. Passport and visa.",
        "Termin bei Dr. Müller im Rathaus.",
        "Das Semester beginnt am 1. Oktober in Deggendorf.",
        "Im 2. Semester gibt es Prüfungen.",
        "Die Gebühr bzw. Der Beitrag ist fällig.",
    ],
)
def test_split_sentences_keeps_abbreviations_and_ordinals(text: str) -> None:
    assert split_sentences(text) == [text]


def test_split_sentences_keeps_closing_quote() -> None:
    assert split_sentences('Er sagte "Hallo." Dann ging er.') == [
        'Er sagte "Hallo."',
        "Dann ging er.",
    ]


# ------------------------------------------------------------------- sections


def test_split_sections_heading_path_and_title_h1() -> None:
    text = (
        "# Test Doc\n"
        "Intro text.\n"
        "### Visa\n"
        "### EU students\n"
        "No visa needed.\n"
        "### Non-EU students\n"
        "Visa needed.\n"
    )
    sections = split_sections(text, title="Test Doc")
    assert [s.heading for s in sections] == ["", "Visa > EU students", "Non-EU students"]
    assert sections[1].lines == ("No visa needed.",)


def test_split_sections_drops_empty_sections() -> None:
    assert split_sections("## Only a heading\n\n## Another one\n") == []


# ------------------------------------------------------------------- chunking


def test_chunk_sizes_respect_budget(long_doc: dict) -> None:
    chunker = Chunker(count, chunk_tokens=100, overlap=0.15)
    chunks = chunker.chunk(long_doc)
    assert len(chunks) > 4
    assert all(c.n_tokens <= 100 for c in chunks)
    assert all(c.n_tokens == count(c.text) for c in chunks)
    # Greedy packing: every chunk except the last of a section is reasonably full.
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        if prev.section == nxt.section:
            assert prev.n_tokens >= 100 - 12 - 1  # cannot fit one more 12-word sentence


def test_consecutive_chunks_overlap(long_doc: dict) -> None:
    chunker = Chunker(count, chunk_tokens=100, overlap=0.15)  # 15 tokens -> one 12-word sentence
    chunks = chunker.chunk(long_doc)
    pairs = [(a, b) for a, b in zip(chunks, chunks[1:], strict=False) if a.section == b.section]
    assert pairs
    for a, b in pairs:
        a_sents = split_sentences(body(a.text))
        b_sents = split_sentences(body(b.text))
        shared = [s for s in b_sents if s in a_sents]
        assert shared, "consecutive chunks of one section must share sentences"
        assert b_sents[: len(shared)] == a_sents[-len(shared) :], "overlap = tail of previous"
        assert sum(count(s) for s in shared) <= 15
        assert len(b_sents) > len(shared), "each chunk must add new content"


def test_no_overlap_across_sections(long_doc: dict) -> None:
    chunks = Chunker(count, chunk_tokens=100, overlap=0.15).chunk(long_doc)
    wohnen = {s for c in chunks if c.section == "Wohnen" for s in split_sentences(body(c.text))}
    vers = {s for c in chunks if c.section == "Versicherung" for s in split_sentences(body(c.text))}
    assert wohnen and vers and not wohnen & vers


def test_zero_overlap_partitions_text(long_doc: dict) -> None:
    chunks = Chunker(count, chunk_tokens=100, overlap=0.0).chunk(long_doc)
    all_sents = [s for c in chunks for s in split_sentences(body(c.text))]
    assert len(all_sents) == len(set(all_sents)) == 65


def test_never_cuts_inside_a_sentence(long_doc: dict) -> None:
    source = set(
        split_sentences(long_doc["text"].replace("## Wohnen", "").replace("## Versicherung", ""))
    )
    for c in Chunker(count, chunk_tokens=100, overlap=0.15).chunk(long_doc):
        for sentence in split_sentences(body(c.text)):
            assert sentence in source


def test_all_text_is_covered(long_doc: dict) -> None:
    chunks = Chunker(count, chunk_tokens=100, overlap=0.15).chunk(long_doc)
    covered = {s for c in chunks for s in split_sentences(body(c.text))}
    assert covered == set(make_sentences(40, tag="A")) | set(make_sentences(25, tag="B"))


def test_no_empty_chunks() -> None:
    text = "## A\n\n\n\n## B\n   \nEin Satz.\n\n## C\n\n"
    chunks = Chunker(count, chunk_tokens=50).chunk(make_doc(text))
    assert len(chunks) == 1
    assert all(body(c.text).strip() for c in chunks)


@pytest.mark.parametrize("text", ["", "   \n\n", "## Nur Überschrift\n"])
def test_empty_documents_give_no_chunks(text: str) -> None:
    assert Chunker(count, chunk_tokens=50).chunk(make_doc(text)) == []


def test_metadata_and_prefix_kept(long_doc: dict) -> None:
    chunks = Chunker(count, chunk_tokens=100).chunk(long_doc)
    for c in chunks:
        assert (c.doc_id, c.title, c.url, c.language) == (
            "doc-1",
            "Test Doc",
            "https://example.org/a",
            "de",
        )
        assert c.section in {"Wohnen", "Versicherung"}
        assert c.text.startswith(f"Test Doc > {c.section}\n\n")
    ids = [c.chunk_id for c in chunks]
    assert ids == [f"doc-1-{i:04d}" for i in range(len(chunks))]
    assert set(chunks[0].to_dict()) >= {
        "chunk_id",
        "doc_id",
        "title",
        "url",
        "language",
        "section",
        "text",
    }


def test_prefix_without_section_is_title_only() -> None:
    chunks = Chunker(count, chunk_tokens=50).chunk(make_doc("Ein Satz ohne Überschrift."))
    assert chunks[0].section == ""
    assert chunks[0].text == "Test Doc\n\nEin Satz ohne Überschrift."


def test_paragraphs_kept_on_separate_lines() -> None:
    text = "## Kosten\nMiete | 450\nEssen | 250\n"
    chunk = Chunker(count, chunk_tokens=50).chunk(make_doc(text))[0]
    assert body(chunk.text) == "Miete | 450\nEssen | 250"


def test_oversized_sentence_is_split_at_words() -> None:
    giant = " ".join(f"w{i}" for i in range(250)) + "."
    chunks = Chunker(count, chunk_tokens=100, overlap=0.0).chunk(make_doc(f"## X\n{giant}"))
    assert len(chunks) >= 3
    assert all(c.n_tokens <= 100 for c in chunks)
    words = [w for c in chunks for w in body(c.text).split()]
    assert words == giant.split()


def test_default_overlap_is_15_percent() -> None:
    assert Chunker(count, chunk_tokens=350).overlap_tokens == round(350 * 0.15)


@pytest.mark.parametrize("kwargs", [{"chunk_tokens": 5}, {"overlap": 0.6}, {"overlap": -0.1}])
def test_invalid_parameters(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        Chunker(count, **kwargs)


def test_chunk_ids_unique_across_sections(long_doc: dict) -> None:
    chunks = Chunker(count, chunk_tokens=100).chunk(long_doc)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all(re.fullmatch(r"doc-1-\d{4}", c.chunk_id) for c in chunks)


def test_section_label_keeps_innermost_two_headings() -> None:
    text = "# Ordnung\n## Kapitel 1\n### § 1 Geltung\nText.\n"
    assert [s.heading for s in split_sections(text)] == ["Kapitel 1 > § 1 Geltung"]


# ------------------------------------------------------- merging small sections

MODULE_GUIDE = (
    "## Modul A\n### Ziele\nKurze Ziele hier.\n### Literatur\nEin Buch.\n"
    "### Prüfung\nKlausur 90 Minuten.\n## Modul B\n### Ziele\nAndere Ziele.\n"
)


def test_small_sibling_sections_are_merged_under_parent() -> None:
    chunks = Chunker(count, chunk_tokens=100).chunk(make_doc(MODULE_GUIDE))
    assert [c.section for c in chunks] == ["Modul A", "Modul B > Ziele"]
    assert body(chunks[0].text) == (
        "Ziele\nKurze Ziele hier.\nLiteratur\nEin Buch.\nPrüfung\nKlausur 90 Minuten."
    )
    assert chunks[0].text.startswith("Test Doc > Modul A\n\n")


def test_large_siblings_are_not_merged() -> None:
    big = " ".join(make_sentences(3))  # 36 words, above the 25-token threshold
    text = f"## Modul\n### Teil 1\n{big}\n### Teil 2\n{big}\n"
    chunks = Chunker(count, chunk_tokens=100).chunk(make_doc(text))
    assert [c.section for c in chunks] == ["Modul > Teil 1", "Modul > Teil 2"]


def test_small_section_joins_large_sibling_if_it_fits() -> None:
    big = " ".join(make_sentences(3))
    text = f"## Modul\n### Inhalt\n{big}\n### Literatur\nEin Buch.\n"
    chunks = Chunker(count, chunk_tokens=100).chunk(make_doc(text))
    assert [c.section for c in chunks] == ["Modul"]
    assert body(chunks[0].text).endswith("Literatur\nEin Buch.")


def test_merging_respects_chunk_budget() -> None:
    parts = "".join(f"### Teil {i}\n{make_sentences(1, words=20)[0]}\n" for i in range(10))
    chunks = Chunker(count, chunk_tokens=100).chunk(make_doc(f"## Modul\n{parts}"))
    assert 1 < len(chunks) < 10
    assert all(c.n_tokens <= 100 and c.section == "Modul" for c in chunks)
    # every sub-section ends up in exactly one chunk, never split between two
    for i in range(10):
        assert sum(f"Teil {i}\n" in c.text for c in chunks) == 1


def test_top_level_sections_are_not_merged() -> None:
    chunks = Chunker(count, chunk_tokens=100).chunk(make_doc("## A\nEins.\n## B\nZwei.\n"))
    assert [c.section for c in chunks] == ["A", "B"]


def test_merging_can_be_disabled() -> None:
    chunker = Chunker(count, chunk_tokens=100, min_section_tokens=0)
    chunks = chunker.chunk(make_doc(MODULE_GUIDE))
    assert [c.section for c in chunks] == [
        "Modul A > Ziele",
        "Modul A > Literatur",
        "Modul A > Prüfung",
        "Modul B > Ziele",
    ]
