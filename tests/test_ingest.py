"""Offline tests for the ingestion helpers: sources, polite fetching, cleanup, language."""

from pathlib import Path

import httpx
import pymupdf
import pytest

from app.ingest.extract import clean_text, extract_html, extract_pdf, remove_repeated_lines
from app.ingest.fetcher import FetchError, PoliteFetcher, looks_like_block_page
from app.ingest.language import detect_language
from app.ingest.sources import load_sources, make_doc_id

# -------------------------------------------------------------------- sources


def test_load_sources_validates_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "- url: https://example.org/a\n  type: html\n  title: A\n"
        "- url: https://example.org/b.pdf\n  type: PDF\n"
        "- url: https://example.org/a\n  type: html\n",
        encoding="utf-8",
    )
    sources = load_sources(path)
    assert [(s.url, s.type, s.title) for s in sources] == [
        ("https://example.org/a", "html", "A"),
        ("https://example.org/b.pdf", "pdf", None),
    ]


@pytest.mark.parametrize(
    "entry", ["- url: ftp://x.org/a\n  type: html\n", "- url: https://x.org/a\n  type: doc\n"]
)
def test_load_sources_rejects_bad_entries(tmp_path: Path, entry: str) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(entry, encoding="utf-8")
    with pytest.raises(ValueError):
        load_sources(path)


def test_doc_id_is_stable_and_safe() -> None:
    url = "https://www.th-deg.de/F%C3%BCr%20Internationals/living-costs-2024.pdf"
    assert make_doc_id(url) == make_doc_id(url)
    assert make_doc_id(url).startswith("th-deg-de-living-costs-2024-")
    assert make_doc_id(url) != make_doc_id(url + "?v=2")


# -------------------------------------------------------------------- fetcher


def make_fetcher(handler, sleeps: list[float]) -> PoliteFetcher:
    """Fetcher with a mocked network, a frozen clock and a sleep that only records."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PoliteFetcher(
        "TestBot/1.0", delay=1.0, client=client, sleep=sleeps.append, clock=lambda: 0.0
    )


def test_fetcher_respects_robots_txt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    sleeps: list[float] = []
    fetcher = make_fetcher(handler, sleeps)
    assert fetcher.fetch("https://example.org/public").content == b"<html>ok</html>"
    with pytest.raises(FetchError, match="robots"):
        fetcher.fetch("https://example.org/private/page")


def test_fetcher_waits_between_requests_to_same_host() -> None:
    sleeps: list[float] = []
    fetcher = make_fetcher(
        lambda r: httpx.Response(404 if r.url.path == "/robots.txt" else 200), sleeps
    )
    fetcher.fetch("https://example.org/a")
    fetcher.fetch("https://example.org/b")
    # robots.txt -> /a -> /b: two waits of the full delay (clock is frozen at 0)
    assert sleeps == [1.0, 1.0]


def test_fetcher_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404 if request.url.path == "/robots.txt" else 500)

    with pytest.raises(FetchError, match="HTTP 500"):
        make_fetcher(handler, []).fetch("https://example.org/a")


def test_fetcher_treats_robots_5xx_as_disallow() -> None:
    with pytest.raises(FetchError, match="robots"):
        make_fetcher(lambda r: httpx.Response(503), []).fetch("https://example.org/a")


# -------------------------------------------------------------------- cleanup


def test_clean_text_drops_cookie_banner_and_boilerplate() -> None:
    raw = (
        "## Wohnen\n"
        "Wir verwenden Cookies, um die Seite zu verbessern. Alle akzeptieren\n"
        "Das Studentenwerk vermietet Zimmer.\n\n\n\n"
        "**Wichtig:** Früh bewerben.\n"
        "Nach oben\n"
    )
    assert clean_text(raw) == (
        "## Wohnen\nDas Studentenwerk vermietet Zimmer.\n\nWichtig: Früh bewerben."
    )


def test_remove_repeated_lines_drops_shared_footer() -> None:
    footer = "Technische Hochschule Deggendorf · Dieter-Görlitz-Platz 1"
    texts = [f"Seite {i} Inhalt.\n{footer}" for i in range(4)]
    assert remove_repeated_lines(texts) == [f"Seite {i} Inhalt." for i in range(4)]


def test_extract_html_keeps_headings_drops_nav() -> None:
    html = b"""<html><head><title>Wohnen | THD</title></head><body>
    <nav><ul><li><a href="/">Startseite</a></li><li><a href="/x">Studium</a></li></ul></nav>
    <main><article><h2>Wohnheime</h2>
    <p>Das Studentenwerk Niederbayern/Oberpfalz betreibt mehrere Wohnheime in Deggendorf.
    Die Miete liegt zwischen 250 und 400 Euro im Monat, inklusive Nebenkosten und Internet.</p>
    <h2>Private Zimmer</h2>
    <p>Private Wohnungen findest du auf den bekannten Portalen. Beginne frueh mit der Suche,
    denn zum Semesterstart ist die Nachfrage in Deggendorf sehr hoch.</p></article></main>
    <footer>Impressum | Datenschutz</footer></body></html>"""
    result = extract_html(html, url="https://example.org/wohnen")
    assert "## Wohnheime" in result.text or "### Wohnheime" in result.text
    assert "Startseite" not in result.text and "Impressum" not in result.text
    assert result.title and result.title.startswith("Wohnen")


# ------------------------------------------------------------------- language


def test_detect_language() -> None:
    assert (
        detect_language("Die Anmeldung beim Bürgeramt muss innerhalb von zwei Wochen erfolgen.")
        == "de"
    )
    assert detect_language("You must register at the residents' office within two weeks.") == "en"
    assert detect_language("ok") == "unknown"


def test_fetcher_rejects_bot_protection_page() -> None:
    challenge = "<!DOCTYPE html><html><head><title>Radware Page</title></head>"
    challenge += "<body>Incident ID: 123</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=challenge, headers={"content-type": "text/html"})

    with pytest.raises(FetchError, match="bot protection"):
        make_fetcher(handler, []).fetch("https://example.org/a")


def test_block_page_detection_ignores_normal_pages() -> None:
    assert not looks_like_block_page(b"<!DOCTYPE html><html><title>Wohnen</title>captcha form")
    assert not looks_like_block_page(b"%PDF-1.7 Incident ID:")


def test_clean_text_undoes_markdown_escapes() -> None:
    assert clean_text(r"1\. Gehe zur Webseite\!") == "1. Gehe zur Webseite!"


# ------------------------------------------------------------------------ PDF


def make_regulation_pdf() -> bytes:
    """3-page PDF: big title, bold two-line '§' heading, hyphenated wrapped body text,
    a superscript sentence number and a running footer with page numbers."""
    doc = pymupdf.open()
    for n in range(1, 4):
        page = doc.new_page()
        if n == 1:
            page.insert_text((72, 60), "Prüfungsordnung", fontsize=20, fontname="helv")
            page.insert_text((72, 100), "§ 4", fontsize=11, fontname="hebo")
            page.insert_text((72, 114), "Prüfungskommission", fontsize=11, fontname="hebo")
            page.insert_text((72, 135), "Die Kommission besteht aus drei Mit-", fontsize=10)
            page.insert_text((72, 147), "gliedern der Fakultät.", fontsize=10)
            page.insert_text((72, 157), "2", fontsize=6)
            page.insert_text((76, 159), "Sie wird vom Senat bestellt.", fontsize=10)
        else:
            page.insert_text((72, 60), f"Weitere Regelungen auf Seite {n}.", fontsize=10)
        page.insert_text((72, 800), "Musterhochschule Deggendorf – Satzung", fontsize=8)
        page.insert_text((500, 800), f"Seite {n}", fontsize=8)
    content = doc.tobytes()
    doc.close()
    return content


def test_extract_pdf_structure() -> None:
    result = extract_pdf(make_regulation_pdf())
    lines = result.text.split("\n")
    assert lines[0] == "# Prüfungsordnung"
    assert lines[1] == "## § 4 Prüfungskommission"
    assert (
        lines[2]
        == "Die Kommission besteht aus drei Mitgliedern der Fakultät. Sie wird vom Senat bestellt."
    )
    assert "Musterhochschule" not in result.text and "Seite 1" not in result.text
    assert result.title == "Prüfungsordnung"
