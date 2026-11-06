"""Bounded, process-local attempt limiter. All untrusted forwarding headers are ignored."""

import math
import time
from threading import Lock

from app.errors import RateLimitError


class RateLimiter:
    def __init__(self, clock=time.monotonic, capacity: int = 10000):
        self.clock, self.capacity = clock, capacity
        self.entries: dict[str, tuple[int, float]] = {}
        self.lock = Lock()

    def consume(self, key: str, limit: int, seconds: int) -> None:
        with self.lock:
            now = self.clock()
            count, expires = self.entries.get(key, (0, now + seconds))
            if expires <= now:
                count, expires = 0, now + seconds
            if key not in self.entries and len(self.entries) >= self.capacity:
                self.entries = {k: v for k, v in self.entries.items() if v[1] > now}
                if len(self.entries) >= self.capacity:
                    raise RateLimitError(
                        "rate_limited", "请求过于频繁，请稍后重试。", retry_after=60
                    )
            if count >= limit:
                raise RateLimitError(
                    "rate_limited",
                    "请求过于频繁，请稍后重试。",
                    retry_after=max(1, math.ceil(expires - now)),
                )
            self.entries[key] = count + 1, expires
