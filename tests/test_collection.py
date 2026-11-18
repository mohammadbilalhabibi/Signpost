"""Tests for ingesting a local source collection (sources.json + text/ + documents/)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import pytest

from app.ingest.chunker import Chunker, whitespace_token_counter
from app.ingest.collection import (
    CollectionError,
    extract_links,
    ingest_collection,
    load_collection,
    load_document,
    parse_front_matter,
)
from app.ingest.jsonl import read_jsonl

ENGLISH = (
    "Have you received a letter of admission? Log in to the Primuss portal and upload a "
    "passport photo. Then confirm your application for enrolment before the deadline."
)


def entry(sid: str, **overrides) -> dict:
    base = {
        "id": sid,
        "title": f"Title {sid}",
        "source_url": f"https://example.org/{sid}",
        "publisher": "Deggendorf Institute of Technology",
        "topic": "enrolment",
        "geographic_scope": "Deggendorf",
        "source_format": "webpage",
        "note": f"Note for {sid}",
        "language": "en",
        "accessed_at": "2026-11-18",
        "ingest": True,
        "pdf_path": f"documents/{sid}.pdf",
        "text_path": f"text/{sid}.md",
        "source_document_date": None,
        "edition_or_period": None,
        "source_language": "en",
    }
    return {**base, **overrides}


def write_text(root: Path, sid: str, body: str, front_id: str | None = None) -> None:
    (root / "text").mkdir(parents=True, exist_ok=True)
    front = f'---\nid: "{front_id or sid}"\ntitle: "Title {sid}"\n---\n\n'
    (root / "text" / f"{sid}.md").write_text(front + body, encoding="utf-8")


def write_pdf(root: Path, sid: str, text: str) -> str:
    (root / "documents").mkdir(parents=True, exist_ok=True)
    path = root / "documents" / f"{sid}.pdf"
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=11)
    doc.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_collection(root: Path, entries: list[dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "sources.json").write_text(json.dumps({"sources": entries}), encoding="utf-8")
    return root


def chunker() -> Chunker:
    return Chunker(whitespace_token_counter, chunk_tokens=120, overlap=0.15)


# ---------------------------------------------------------------- loading


def test_only_ingest_true_sources_are_used_once(tmp_path: Path) -> None:
    root = tmp_path / "c"
    write_text(root, "D01", f"# Title D01\n\n## How to enrol\n\n{ENGLISH}\n")
    write_pdf(root, "D01", "PDF copy that must not be indexed in addition to the text copy.")
    write_text(root, "R01", f"## Flyer\n\n{ENGLISH}\n")
    make_collection(root, [entry("D01"), entry("R01", ingest=False)])

    report = ingest_collection(root, tmp_path / "out", chunker())

    assert [d["doc_id"] for d in report.documents] == ["D01"]
    assert report.documents[0]["representation"] == "text"
    texts = " ".join(c.text for c in report.chunks)
    assert "PDF copy" not in texts and "Primuss" in texts
    assert {c.doc_id for c in report.chunks} == {"D01"}


def test_metadata_is_carried_into_every_chunk(tmp_path: Path) -> None:
    root = tmp_path / "c"
    write_text(root, "D05", f"## Dates\n\n{ENGLISH}\n\n## Fees\n\n{ENGLISH}\n")
    make_collection(
        root,
        [entry("D05", edition_or_period="Summer semester 2027", source_document_date="2026-10-01")],
    )
    ingest_collection(root, tmp_path / "out", chunker())

    chunks = list(read_jsonl(tmp_path / "out" / "chunks.jsonl"))
    assert len(chunks) >= 2
    for c in chunks:
        assert c["url"] == "https://example.org/D05"  # original URL, not the local file
        assert c["meta"]["source_id"] == "D05"
        assert c["meta"]["edition_or_period"] == "Summer semester 2027"
        assert c["meta"]["source_document_date"] == "2026-10-01"
        assert c["meta"]["publisher"] == "Deggendorf Institute of Technology"
        assert c["meta"]["note"] == "Note for D05"
        assert c["language"] == "en"


def test_pdf_is_used_when_there_is_no_text_copy(tmp_path: Path) -> None:
    root = tmp_path / "c"
    digest = write_pdf(root, "D02", ENGLISH)
    make_collection(root, [entry("D02", text_path=None, sha256=digest)])
    doc = load_document(load_collection(root)[0], root)
    assert doc["representation"] == "pdf" and "Primuss" in doc["text"]


def test_pdf_with_wrong_checksum_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "c"
    write_pdf(root, "D02", ENGLISH)
    make_collection(root, [entry("D02", text_path=None, sha256="0" * 64)])
    with pytest.raises(CollectionError, match="SHA-256"):
        load_document(load_collection(root)[0], root)


@pytest.mark.parametrize(
    "path",
    ["reference_only/R01.md", "README.md", "evaluation_questions.json", "../outside.md"],
)
def test_documentation_and_reference_files_are_never_corpus(tmp_path: Path, path: str) -> None:
    root = tmp_path / "c"
    make_collection(root, [entry("X1", text_path=path, pdf_path=None)])
    with pytest.raises(CollectionError, match="not an allowed corpus file"):
        load_document(load_collection(root)[0], root)


def test_non_english_content_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "c"
    german = (
        "Nach dem Umzug müssen Sie Ihren Wohnsitz innerhalb von zwei Wochen beim Bürgeramt "
        "anmelden. Bringen Sie Ihren Personalausweis und die Wohnungsgeberbestätigung mit."
    )
    write_text(root, "D30", f"## Anmeldung\n\n{german}\n")
    make_collection(root, [entry("D30")])
    report = ingest_collection(root, tmp_path / "out", chunker())
    assert report.documents == [] and report.failed[0][0] == "D30"


def test_front_matter_id_must_match(tmp_path: Path) -> None:
    root = tmp_path / "c"
    write_text(root, "D01", ENGLISH, front_id="D99")
    make_collection(root, [entry("D01")])
    with pytest.raises(CollectionError, match="D99"):
        load_document(load_collection(root)[0], root)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    root = make_collection(tmp_path / "c", [entry("D01"), entry("D01")])
    with pytest.raises(CollectionError, match="duplicate"):
        load_collection(root)


# ------------------------------------------------------------------ parsing


def test_parse_front_matter() -> None:
    meta, body = parse_front_matter('---\nid: "D01"\nsource_document_date: null\n---\n\n# T\n')
    assert meta == {"id": "D01", "source_document_date": None}
    assert body == "# T\n"
    assert parse_front_matter("# No front matter") == ({}, "# No front matter")


def test_link_lines_move_to_metadata_and_attach_to_their_chunk(tmp_path: Path) -> None:
    body = (
        "## Documents\n\n- Application of Enrollment\n\n"
        "[Application of Enrollment](https://example.org/form.pdf)\n\n"
        "- Contact: jane@example.org\n\n[jane@example.org](mailto:jane@example.org)\n\n"
        "See the [online portal](https://example.org/portal) for payment.\n"
    )
    text, links = extract_links(body)
    assert "https://" not in text and "mailto:" not in text
    assert "See the online portal for payment." in text
    assert [(link["text"], link["anchor"]) for link in links] == [
        ("Application of Enrollment", "- Application of Enrollment"),
        ("online portal", "See the [online portal](https://example.org/portal) for payment."),
    ]

    root = tmp_path / "c"
    write_text(root, "D01", f"{ENGLISH}\n\n{body}")
    make_collection(root, [entry("D01")])
    report = ingest_collection(root, tmp_path / "out", chunker())
    urls = {link["url"] for c in report.chunks for link in c.meta.get("links", [])}
    assert "https://example.org/form.pdf" in urls
