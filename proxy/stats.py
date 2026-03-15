"""
stats.py – Thread-safe global stats collector for the proxy.
Tracks requests, bytes, connections, and recent request log.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class RequestRecord:
    timestamp: float
    method: str
    host: str
    port: int
    protocol: str          # HTTP | HTTPS | SOCKS5 | FTP
    status: str            # OK | BLOCKED | ERROR
    bytes_sent: int = 0


class ProxyStats:
    def __init__(self, max_log: int = 200):
        self._lock = threading.Lock()
        self.start_time: float = time.time()

        # Counters
        self.total_requests: int = 0
        self.blocked_requests: int = 0
        self.error_requests: int = 0
        self.cache_hits: int = 0
        self.total_bytes: int = 0
        self.active_connections: int = 0
        self.peak_connections: int = 0

        # Rolling request log (most recent last)
        self._log: Deque[RequestRecord] = deque(maxlen=max_log)

    # ── Recording ────────────────────────────────────────────────────────────

    def record_request(
        self,
        method: str,
        host: str,
        port: int,
        protocol: str,
        status: str,
        bytes_sent: int = 0,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            self.total_bytes += bytes_sent
            if status == "BLOCKED":
                self.blocked_requests += 1
            elif status == "ERROR":
                self.error_requests += 1
            self._log.append(RequestRecord(
                timestamp=time.time(),
                method=method,
                host=host,
                port=port,
                protocol=protocol,
                status=status,
                bytes_sent=bytes_sent,
            ))

    def record_cache_hit(self) -> None:
        with self._lock:
            self.cache_hits += 1

    def connection_opened(self) -> None:
        with self._lock:
            self.active_connections += 1
            if self.active_connections > self.peak_connections:
                self.peak_connections = self.active_connections

    def connection_closed(self) -> None:
        with self._lock:
            self.active_connections = max(0, self.active_connections - 1)

    # ── Snapshot ─────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            uptime = int(time.time() - self.start_time)
            return {
                "uptime_sec": uptime,
                "uptime_str": _fmt_uptime(uptime),
                "total_requests": self.total_requests,
                "blocked_requests": self.blocked_requests,
                "error_requests": self.error_requests,
                "cache_hits": self.cache_hits,
                "total_bytes": self.total_bytes,
                "total_bytes_str": _fmt_bytes(self.total_bytes),
                "active_connections": self.active_connections,
                "peak_connections": self.peak_connections,
                "log": list(self._log),
            }

    def reset(self) -> None:
        with self._lock:
            self.start_time = time.time()
            self.total_requests = 0
            self.blocked_requests = 0
            self.error_requests = 0
            self.cache_hits = 0
            self.total_bytes = 0
            self.active_connections = 0
            self.peak_connections = 0
            self._log.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────
STATS = ProxyStats()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_uptime(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
