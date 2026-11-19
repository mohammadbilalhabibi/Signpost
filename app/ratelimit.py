"""Small in-memory limiters: per-client sliding window and one global daily budget."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta


class RateLimiter:
    """Allow at most ``limit`` calls per ``window`` seconds for each key (e.g. client IP)."""

    def __init__(
        self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record a call for ``key``; return None if allowed, else seconds until the next slot."""
        now = self.clock()
        with self._lock:
            calls = self._calls[key]
            while calls and calls[0] <= now - self.window:
                calls.popleft()
            if len(calls) >= self.limit:
                return max(1, math.ceil(calls[0] + self.window - now))
            calls.append(now)
            if len(self._calls) > 10_000:  # forget idle clients so memory stays bounded
                for idle in [k for k, v in self._calls.items() if not v]:
                    del self._calls[idle]
            return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DailyLimiter:
    """One budget of LLM-answered questions per UTC day, shared by all users.

    ``acquire()`` reserves a slot before the (paid) LLM call and ``release()`` gives it back
    when no LLM call happened, so concurrent requests can never exceed the limit. The count
    lives in memory: it resets at 00:00 UTC and when the process restarts. ``limit`` 0 = off.
    """

    def __init__(self, limit: int, now: Callable[[], datetime] = _utc_now) -> None:
        self.limit = limit
        self.now = now
        self._day = now().date()
        self._used = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        today = self.now().date()
        if today != self._day:
            self._day, self._used = today, 0

    @property
    def used(self) -> int:
        """Slots used today."""
        with self._lock:
            self._roll()
            return self._used

    def acquire(self) -> bool:
        """Reserve one slot; False if today's budget is used up (always True when off)."""
        with self._lock:
            self._roll()
            if self.limit > 0 and self._used >= self.limit:
                return False
            self._used += 1
            return True

    def release(self) -> None:
        """Return a reserved slot (the question did not call the LLM)."""
        with self._lock:
            self._roll()
            self._used = max(0, self._used - 1)

    def seconds_until_reset(self) -> int:
        """Seconds until the budget resets at the next 00:00 UTC."""
        now = self.now()
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
        return max(1, math.ceil((midnight - now).total_seconds()))
