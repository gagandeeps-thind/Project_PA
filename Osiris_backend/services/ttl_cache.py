"""A small in-process cache for results that are expensive to compute and fine to serve slightly stale.

Per process: with several API workers each keeps its own copy, which only means each worker
computes a result once per TTL. Values must be treated as read-only by callers; copy before
changing them.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Callable, Hashable, TypeVar

import settings

T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 256, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[Hashable, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_compute(self, key: Hashable, compute: Callable[[], T]) -> T:
        if self.ttl_seconds <= 0:
            return compute()
        now = self._clock()
        with self._lock:
            hit = self._entries.get(key)
            if hit is not None and hit[0] > now:
                self._entries.move_to_end(key)
                return hit[1]  # type: ignore[return-value]
        # Computed outside the lock: two threads may both compute one key, which is cheaper than
        # making every other key wait behind a slow query.
        value = compute()
        with self._lock:
            self._entries[key] = (now + self.ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def ttl_from_env(name: str, default: float) -> float:
    """`name` in seconds. Off under OSIRIS_ENV=test unless set, so suites see their own writes at once."""
    raw = os.environ.get(name)
    if raw is not None:
        return float(raw)
    return 0.0 if settings.environment() == "test" else default
