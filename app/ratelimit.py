"""Small in-memory sliding-window rate limiter.

Good for one process. Behind several workers or hosts, move this to a shared store (e.g. Redis).
"""
import threading
import time
from collections import defaultdict, deque

from app import config

_hits = defaultdict(deque)
_lock = threading.Lock()


def allow(bucket, client_id, now=None):
    limit, window = config.RATE_LIMITS[bucket]
    now = time.monotonic() if now is None else now
    key = (bucket, client_id)
    with _lock:
        q = _hits[key]
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset():
    with _lock:
        _hits.clear()
