"""A small in-memory sliding-window rate limiter (per process, per client key)."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


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
