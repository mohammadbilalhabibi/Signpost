"""Polite HTTP downloader: honours robots.txt, waits between requests, identifies itself."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024  # refuse anything larger than 50 MB

# Bot-protection / challenge pages that some sites return with HTTP 200. We never
# try to get past them; the source is reported as failed instead.
_BLOCK_PAGE_MARKERS = (
    b"<title>radware page</title>",
    b"incident id:",
    b"cf-browser-verification",
    b"<title>just a moment...</title>",
    b"<title>access denied</title>",
)


class FetchError(Exception):
    """A source could not be downloaded (network error, HTTP error, robots.txt, ...)."""


@dataclass(frozen=True)
class FetchResult:
    """A downloaded resource."""

    url: str
    final_url: str
    content: bytes
    content_type: str
    fetched_at: str  # ISO 8601, UTC


class PoliteFetcher:
    """Downloads URLs one at a time while respecting robots.txt and a per-host delay.

    ``sleep`` and ``clock`` are injectable so tests run without real waiting.
    """

    def __init__(
        self,
        user_agent: str,
        delay: float = 1.0,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.user_agent = user_agent
        self.delay = delay
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self._sleep = sleep
        self._clock = clock
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch(self, url: str) -> FetchResult:
        """Download ``url``; raise FetchError if disallowed or failed."""
        if not self.allowed(url):
            raise FetchError("disallowed by robots.txt")
        response = self._get(url)
        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code}")
        if len(response.content) > MAX_BYTES:
            raise FetchError(f"response larger than {MAX_BYTES} bytes")
        if looks_like_block_page(response.content):
            raise FetchError("blocked by the site's bot protection (not bypassed)")
        return FetchResult(
            url=url,
            final_url=str(response.url),
            content=response.content,
            content_type=response.headers.get("content-type", "").split(";")[0].strip().lower(),
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def allowed(self, url: str) -> bool:
        """Return True if robots.txt of the URL's host allows our user agent to fetch it."""
        return self._robots_for(url).can_fetch(self.user_agent, url)

    def _robots_for(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]

        parser = RobotFileParser(f"{origin}/robots.txt")
        try:
            response = self._get(f"{origin}/robots.txt")
            status = response.status_code
        except FetchError as exc:
            logger.warning(
                "robots.txt unreachable for %s (%s); treating host as disallowed", origin, exc
            )
            status = 503
        # RFC 9309: 4xx -> no restrictions; 5xx / unreachable -> assume full disallow.
        if status >= 500:
            parser.parse(["User-agent: *", "Disallow: /"])
        elif status >= 400:
            parser.parse([])
        else:
            parser.parse(response.text.splitlines())
        self._robots[origin] = parser
        return parser

    def _wait_for_host(self, host: str) -> None:
        delay = self.delay
        parser = self._robots.get(host)
        crawl_delay = parser.crawl_delay(self.user_agent) if parser else None
        if crawl_delay:
            delay = max(delay, float(crawl_delay))
        last = self._last_request.get(host)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)

    def _get(self, url: str) -> httpx.Response:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        self._wait_for_host(origin)
        try:
            return self._client.get(url)
        except httpx.HTTPError as exc:
            raise FetchError(f"{type(exc).__name__}: {exc}") from exc
        finally:
            self._last_request[origin] = self._clock()


def looks_like_block_page(content: bytes) -> bool:
    """True if an HTML response is a bot-protection / challenge page instead of content."""
    head = content[:20000].lower()
    if not head.lstrip().startswith((b"<!doctype html", b"<html")):
        return False
    return any(marker in head for marker in _BLOCK_PAGE_MARKERS)
