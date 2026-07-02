import time
from collections import defaultdict
from collections.abc import Sequence


class RateLimiter:
    def __init__(self, max_requests: int = 5, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self._buckets: dict[int, list[float]] = defaultdict(list)

    def _cleanup(self, key: int, now: float) -> None:
        cutoff = now - self.window
        timestamps = self._buckets.get(key, [])
        self._buckets[key] = [t for t in timestamps if t > cutoff]

    def check(self, key: int) -> bool:
        now = time.time()
        self._cleanup(key, now)
        return len(self._buckets.get(key, [])) < self.max_requests

    def record(self, key: int) -> None:
        now = time.time()
        self._buckets[key].append(now)

    def get_history(self, key: int) -> Sequence[float]:
        self._cleanup(key, time.time())
        return list(self._buckets.get(key, []))
