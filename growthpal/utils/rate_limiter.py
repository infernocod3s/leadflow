"""Token bucket rate limiter for async operations."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Token bucket rate limiter.

    Args:
        rate: Number of tokens added per second.
        max_tokens: Maximum bucket size.
    """

    def __init__(self, rate: float, max_tokens: int | None = None):
        self.rate = rate
        self.max_tokens = max_tokens or int(rate)
        self._tokens = float(self.max_tokens)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.max_tokens, self._tokens + elapsed * self.rate)
        self._last_refill = now

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
            # Wait a bit before retrying
            await asyncio.sleep(1.0 / self.rate)
