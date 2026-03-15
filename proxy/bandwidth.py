"""
bandwidth.py – Token-bucket throttler, applied per client IP.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from .config import BandwidthConfig
from .logger import get_logger

log = get_logger("proxy.bandwidth")

CHUNK = 4096


class TokenBucket:
    def __init__(self, rate_kbps: int):
        self.rate = rate_kbps * 1024
        self._tokens = float(self.rate)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, n_bytes: int) -> None:
        if self.rate <= 0:
            return
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self.rate, self._tokens + elapsed * self.rate)
            if self._tokens >= n_bytes:
                self._tokens -= n_bytes
            else:
                deficit = n_bytes - self._tokens
                time.sleep(deficit / self.rate)
                self._tokens = 0


class BandwidthManager:
    def __init__(self, cfg: BandwidthConfig):
        self.enabled = cfg.enabled if cfg.enabled is not None else True
        self.default_kbps = cfg.default_kbps or 0
        self.per_ip_kbps: Dict[str, int] = cfg.per_ip or {}
        self._buckets: Dict[str, Optional[TokenBucket]] = {}
        self._lock = threading.Lock()

    def get_bucket(self, ip: str) -> Optional[TokenBucket]:
        if not self.enabled:
            return None
        with self._lock:
            if ip not in self._buckets:
                kbps = self.per_ip_kbps.get(ip, self.default_kbps)
                self._buckets[ip] = TokenBucket(kbps) if kbps > 0 else None
            return self._buckets[ip]

    def throttled_send(self, sock, data: bytes, ip: str) -> None:
        bucket = self.get_bucket(ip)
        if bucket is None:
            sock.sendall(data)
            return
        offset = 0
        while offset < len(data):
            chunk = data[offset: offset + CHUNK]
            bucket.consume(len(chunk))
            sock.sendall(chunk)
            offset += len(chunk)
