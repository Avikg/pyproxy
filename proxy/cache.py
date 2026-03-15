"""
cache.py – Simple thread-safe in-memory LRU cache for HTTP GET responses.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple

from .config import CacheConfig
from .logger import get_logger

log = get_logger("proxy.cache")


@dataclass
class CacheEntry:
    status_line: bytes
    headers: bytes
    body: bytes
    expires: float          # monotonic timestamp


class ResponseCache:
    def __init__(self, cfg: CacheConfig):
        self.enabled = cfg.enabled
        self.max_size = cfg.max_size
        self.ttl = cfg.ttl
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[CacheEntry]:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires:
                del self._store[key]
                log.debug("Cache expired: %s", key)
                return None
            # Move to end (most-recently used)
            self._store.move_to_end(key)
            log.debug("Cache HIT: %s", key)
            return entry

    def put(self, key: str, status_line: bytes, headers: bytes, body: bytes) -> None:
        if not self.enabled:
            return
        with self._lock:
            # Evict LRU if at capacity
            while len(self._store) >= self.max_size:
                evicted, _ = self._store.popitem(last=False)
                log.debug("Cache evict (LRU): %s", evicted)
            self._store[key] = CacheEntry(
                status_line=status_line,
                headers=headers,
                body=body,
                expires=time.monotonic() + self.ttl,
            )
            log.debug("Cache STORE: %s", key)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    @staticmethod
    def make_key(method: str, host: str, path: str) -> str:
        return f"{method.upper()}|{host}|{path}"

    def stats(self) -> Tuple[int, int]:
        """Return (current_size, max_size)."""
        with self._lock:
            return len(self._store), self.max_size
