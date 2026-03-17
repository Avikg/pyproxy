"""
server.py – Thread-pool TCP server with DNS cache and IPv6 fallback handling.
"""
from __future__ import annotations

import signal
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Tuple

from .bandwidth import BandwidthManager
from .cache import ResponseCache
from .config import Config
from .filters import DomainFilter, IPFilter
from .handler import ProxyHandler
from .logger import get_logger, setup_logging

log = get_logger("proxy.server")

# ── DNS cache to avoid repeated lookups slowing things down ──────────────────
@lru_cache(maxsize=1024)
def _cached_resolve(host: str) -> str:
    """Resolve hostname once and cache. Returns IP or original host on failure."""
    try:
        # Prefer IPv4 — getaddrinfo with AF_INET avoids IPv6 timeout issues
        results = socket.getaddrinfo(host, None, socket.AF_INET,
                                     socket.SOCK_STREAM)
        if results:
            return results[0][4][0]
    except socket.gaierror:
        pass
    try:
        # Fallback: any address family
        return socket.gethostbyname(host)
    except socket.gaierror:
        return host  # let connect() fail with a clear error


# Patch socket.create_connection to use our DNS cache
_orig_create_connection = socket.create_connection

def _fast_create_connection(address: Tuple[str, int], timeout=None, **kw):
    host, port = address
    resolved = _cached_resolve(host)
    return _orig_create_connection((resolved, port), timeout=timeout, **kw)

socket.create_connection = _fast_create_connection


class ProxyServer:
    def __init__(self, config: Config):
        self.config = config
        setup_logging(config.logging)

        self.ip_filter     = IPFilter(config.ip_filter)
        self.domain_filter = DomainFilter(config.domain_filter)
        self.cache         = ResponseCache(config.cache)
        self.bandwidth     = BandwidthManager(config.bandwidth)

        self._stop_event   = threading.Event()
        self._server_sock: socket.socket | None = None

    def start(self) -> None:
        host    = self.config.server.host
        port    = self.config.server.port
        workers = self.config.server.workers

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Reduce accept backlog latency
        self._server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._server_sock.bind((host, port))
        self._server_sock.listen(256)
        self._server_sock.settimeout(1.0)

        log.info("=" * 60)
        log.info("Avik Proxy started on %s:%d  (workers=%d)", host, port, workers)
        log.info("Cache: %s  |  Bandwidth: %s  |  DNS cache: ON",
                 self.config.cache.enabled, self.config.bandwidth.enabled)
        log.info("IP filter: %s  |  Domain filter: %s",
                 self.config.ip_filter.mode, self.config.domain_filter.mode)
        log.info("=" * 60)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._signal_handler)
            except (OSError, ValueError):
                pass

        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="worker") as pool:
            while not self._stop_event.is_set():
                try:
                    client_sock, client_addr = self._server_sock.accept()
                    # Disable Nagle — reduces latency for small packets
                    client_sock.setsockopt(
                        socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    pool.submit(self._dispatch, client_sock, client_addr)
                except socket.timeout:
                    continue
                except OSError:
                    break

        log.info("Avik Proxy stopped.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass

    def _dispatch(self, client_sock: socket.socket,
                  client_addr: tuple) -> None:
        ProxyHandler(
            client_sock=client_sock,
            client_addr=client_addr,
            ip_filter=self.ip_filter,
            domain_filter=self.domain_filter,
            cache=self.cache,
            bandwidth=self.bandwidth,
        ).handle()

    def _signal_handler(self, signum, frame) -> None:
        log.info("Signal %d – shutting down.", signum)
        self.stop()