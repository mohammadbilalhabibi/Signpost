"""Tests for the in-memory limiters."""

from __future__ import annotations

from datetime import UTC, datetime

from app.ratelimit import DailyLimiter, RateLimiter


def test_daily_limiter_acquire_release_and_reset() -> None:
    now = [datetime(2026, 11, 19, 12, 0, tzinfo=UTC)]
    limiter = DailyLimiter(2, now=lambda: now[0])
    assert limiter.acquire() and limiter.acquire()
    assert not limiter.acquire()
    limiter.release()
    assert limiter.used == 1 and limiter.acquire()
    assert limiter.seconds_until_reset() == 12 * 3600
    now[0] = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
    assert limiter.used == 0 and limiter.acquire()


def test_daily_limiter_zero_is_unlimited() -> None:
    limiter = DailyLimiter(0)
    assert all(limiter.acquire() for _ in range(1000))


def test_rate_limiter_window() -> None:
    t = [0.0]
    limiter = RateLimiter(2, window=60, clock=lambda: t[0])
    assert limiter.hit("a") is None and limiter.hit("a") is None
    assert limiter.hit("a") == 60 and limiter.hit("b") is None
    t[0] = 61
    assert limiter.hit("a") is None
