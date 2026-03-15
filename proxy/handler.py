"""
handler.py – Per-connection handler: HTTP, HTTPS CONNECT, SOCKS5, FTP-over-HTTP.
Records stats via proxy.stats.STATS singleton.
"""
from __future__ import annotations

import select
import socket
import struct

from .bandwidth import BandwidthManager
from .cache import ResponseCache
from .filters import DomainFilter, IPFilter
from .ftp_handler import handle_ftp_request
from .http_parser import HTTPRequest, parse_request, recv_until
from .logger import get_logger
from .stats import STATS

log = get_logger("proxy.handler")

BUFFER = 8192
TIMEOUT = 30

SOCKS5_VER      = 0x05
SOCKS5_NO_AUTH  = 0x00
SOCKS5_CMD_CONNECT = 0x01
SOCKS5_ATYP_IPV4   = 0x01
SOCKS5_ATYP_DOMAIN = 0x03
SOCKS5_ATYP_IPV6   = 0x04


class ProxyHandler:
    def __init__(self, client_sock, client_addr, ip_filter: IPFilter,
                 domain_filter: DomainFilter, cache: ResponseCache,
                 bandwidth: BandwidthManager):
        self.client     = client_sock
        self.client_ip  = client_addr[0]
        self.ip_filter  = ip_filter
        self.domain_filter = domain_filter
        self.cache      = cache
        self.bandwidth  = bandwidth

    # ── Entry point ──────────────────────────────────────────────────────────

    def handle(self) -> None:
        STATS.connection_opened()
        try:
            self.client.settimeout(TIMEOUT)

            if not self.ip_filter.is_allowed(self.client_ip):
                log.warning("Blocked client IP: %s", self.client_ip)
                STATS.record_request("CONNECT", self.client_ip, 0, "HTTP", "BLOCKED")
                self._send_http_error(403, "Forbidden – IP blocked")
                return

            first = self.client.recv(1, socket.MSG_PEEK)
            if not first:
                return

            if first[0] == SOCKS5_VER:
                self._handle_socks5()
            else:
                self._handle_http()

        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            pass
        except Exception as exc:
            log.debug("Handler error [%s]: %s", self.client_ip, exc)
        finally:
            STATS.connection_closed()
            try:
                self.client.close()
            except Exception:
                pass

    # ── HTTP / HTTPS / FTP ───────────────────────────────────────────────────

    def _handle_http(self) -> None:
        raw = recv_until(self.client)
        if not raw:
            return

        req = parse_request(raw)
        if req is None:
            self._send_http_error(400, "Bad Request")
            return

        log.info("HTTP %s %s:%d%s [%s]", req.method, req.host, req.port, req.path, self.client_ip)

        if not self.domain_filter.is_allowed(req.host):
            log.warning("Blocked domain: %s [%s]", req.host, self.client_ip)
            STATS.record_request(req.method, req.host, req.port, "HTTP", "BLOCKED")
            self._send_http_error(403, "Forbidden – domain blocked")
            return

        if req.target.lower().startswith("ftp://"):
            ftp_port = req.port if req.port != 80 else 21
            handle_ftp_request(self.client, req.host, ftp_port, req.path)
            STATS.record_request(req.method, req.host, ftp_port, "FTP", "OK")
            return

        if req.is_connect:
            self._handle_connect(req.host, req.port)
        else:
            self._handle_plain_http(req, raw)

    def _handle_plain_http(self, req: HTTPRequest, raw: bytes) -> None:
        cache_key = req.cache_key
        cached = self.cache.get(cache_key) if req.method.upper() == "GET" else None

        if cached:
            response = cached.status_line + b"\r\n" + cached.headers + b"\r\n\r\n" + cached.body
            self.bandwidth.throttled_send(self.client, response, self.client_ip)
            STATS.record_cache_hit()
            STATS.record_request(req.method, req.host, req.port, "HTTP", "OK", len(response))
            return

        try:
            remote = self._connect_remote(req.host, req.port)
        except OSError as exc:
            log.error("Cannot reach %s:%d – %s", req.host, req.port, exc)
            STATS.record_request(req.method, req.host, req.port, "HTTP", "ERROR")
            self._send_http_error(502, "Bad Gateway")
            return

        try:
            remote.sendall(self._rewrite_request(raw, req))
            response_raw = self._recv_full_response(remote)
            if response_raw:
                self.bandwidth.throttled_send(self.client, response_raw, self.client_ip)
                STATS.record_request(req.method, req.host, req.port, "HTTP", "OK", len(response_raw))
                if req.method.upper() == "GET":
                    self._cache_response(cache_key, response_raw)
        finally:
            remote.close()

    def _handle_connect(self, host: str, port: int) -> None:
        try:
            remote = self._connect_remote(host, port)
        except OSError as exc:
            log.error("CONNECT failed %s:%d – %s", host, port, exc)
            STATS.record_request("CONNECT", host, port, "HTTPS", "ERROR")
            self._send_http_error(502, "Bad Gateway")
            return

        self.client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        log.info("CONNECT tunnel %s:%d [%s]", host, port, self.client_ip)
        STATS.record_request("CONNECT", host, port, "HTTPS", "OK")
        try:
            self._tunnel(self.client, remote)
        finally:
            remote.close()

    # ── SOCKS5 ───────────────────────────────────────────────────────────────

    def _handle_socks5(self) -> None:
        header = self._recv_exact(2)
        if not header or header[0] != SOCKS5_VER:
            return
        self._recv_exact(header[1])
        self.client.sendall(bytes([SOCKS5_VER, SOCKS5_NO_AUTH]))

        req_header = self._recv_exact(4)
        if not req_header or req_header[1] != SOCKS5_CMD_CONNECT:
            self.client.sendall(b"\x05\x07\x00\x01" + b"\x00" * 6)
            return

        atyp = req_header[3]
        if atyp == SOCKS5_ATYP_IPV4:
            host = socket.inet_ntoa(self._recv_exact(4))
        elif atyp == SOCKS5_ATYP_DOMAIN:
            host = self._recv_exact(self._recv_exact(1)[0]).decode()
        elif atyp == SOCKS5_ATYP_IPV6:
            host = socket.inet_ntop(socket.AF_INET6, self._recv_exact(16))
        else:
            return

        port = struct.unpack("!H", self._recv_exact(2))[0]
        log.info("SOCKS5 CONNECT %s:%d [%s]", host, port, self.client_ip)

        if not self.domain_filter.is_allowed(host):
            log.warning("SOCKS5 blocked domain: %s", host)
            STATS.record_request("CONNECT", host, port, "SOCKS5", "BLOCKED")
            self.client.sendall(b"\x05\x02\x00\x01" + b"\x00" * 6)
            return

        try:
            remote = self._connect_remote(host, port)
        except OSError as exc:
            log.error("SOCKS5 cannot reach %s:%d – %s", host, port, exc)
            STATS.record_request("CONNECT", host, port, "SOCKS5", "ERROR")
            self.client.sendall(b"\x05\x04\x00\x01" + b"\x00" * 6)
            return

        self.client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
        STATS.record_request("CONNECT", host, port, "SOCKS5", "OK")
        try:
            self._tunnel(self.client, remote)
        finally:
            remote.close()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _connect_remote(self, host, port):
        return socket.create_connection((host, port), timeout=TIMEOUT)

    def _tunnel(self, a, b):
        a.settimeout(None)
        b.settimeout(None)
        while True:
            r, _, _ = select.select([a, b], [], [], TIMEOUT)
            if not r:
                break
            for src in r:
                dst = b if src is a else a
                try:
                    data = src.recv(BUFFER)
                    if not data:
                        return
                    dst.sendall(data)
                except OSError:
                    return

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.client.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Client disconnected")
            buf += chunk
        return buf

    def _recv_full_response(self, sock):
        buf = b""
        sock.settimeout(TIMEOUT)
        try:
            while True:
                chunk = sock.recv(BUFFER)
                if not chunk:
                    break
                buf += chunk
        except socket.timeout:
            pass
        return buf

    def _rewrite_request(self, raw, req):
        if not (req.target.startswith("http://") or req.target.startswith("https://")):
            return raw
        old = f"{req.method} {req.target} {req.version}".encode()
        new = f"{req.method} {req.path} {req.version}".encode()
        return raw.replace(old, new, 1)

    def _send_http_error(self, code, message):
        body = f"<h1>{code} {message}</h1>".encode()
        resp = (f"HTTP/1.1 {code} {message}\r\nContent-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body
        try:
            self.client.sendall(resp)
        except OSError:
            pass

    def _cache_response(self, key, raw):
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            return
        lines = raw[:sep].split(b"\r\n")
        self.cache.put(key, lines[0], b"\r\n".join(lines[1:]), raw[sep + 4:])
