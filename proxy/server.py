"""
server.py – Thread-pool TCP server that accepts connections and dispatches ProxyHandler.
"""
from __future__ import annotations

import signal
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

from .bandwidth import BandwidthManager
from .cache import ResponseCache
from .config import Config
from .filters import DomainFilter, IPFilter
from .handler import ProxyHandler
from .logger import get_logger, setup_logging

log = get_logger("proxy.server")


class ProxyServer:
    def __init__(self, config: Config):
        self.config = config
        setup_logging(config.logging)

        self.ip_filter = IPFilter(config.ip_filter)
        self.domain_filter = DomainFilter(config.domain_filter)
        self.cache = ResponseCache(config.cache)
        self.bandwidth = BandwidthManager(config.bandwidth)

        self._stop_event = threading.Event()
        self._server_sock: socket.socket | None = None

    # ------------------------------------------------------------------

    def start(self) -> None:
        host = self.config.server.host
        port = self.config.server.port
        workers = self.config.server.workers

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((host, port))
        self._server_sock.listen(128)
        self._server_sock.settimeout(1.0)   # allows stop_event check

        log.info("=" * 60)
        log.info("PyProxy started on %s:%d  (workers=%d)", host, port, workers)
        log.info("Cache: %s  |  Bandwidth control: %s", self.config.cache.enabled, self.config.bandwidth.enabled)
        log.info("IP filter: %s  |  Domain filter: %s", self.config.ip_filter.mode, self.config.domain_filter.mode)
        log.info("=" * 60)

        # Register SIGINT / SIGTERM for clean shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._signal_handler)
            except (OSError, ValueError):
                pass  # not always possible (e.g. non-main thread)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="worker") as pool:
            while not self._stop_event.is_set():
                try:
                    client_sock, client_addr = self._server_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                pool.submit(self._dispatch, client_sock, client_addr)

        log.info("Server stopped.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass

    # ------------------------------------------------------------------

    def _dispatch(self, client_sock: socket.socket, client_addr: tuple) -> None:
        handler = ProxyHandler(
            client_sock=client_sock,
            client_addr=client_addr,
            ip_filter=self.ip_filter,
            domain_filter=self.domain_filter,
            cache=self.cache,
            bandwidth=self.bandwidth,
        )
        handler.handle()

    def _signal_handler(self, signum, frame) -> None:
        log.info("Signal %d received – shutting down.", signum)
        self.stop()
