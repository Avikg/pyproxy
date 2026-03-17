"""
handler.py - CCProxy-equivalent handler.

Key design decisions matching CCProxy behaviour:
  - CONNECT tunnels run in their OWN thread so one long-lived tunnel
    never blocks the worker from accepting new requests
  - HTTP keep-alive loop is time-bounded (max 30 req or 60s idle)
  - All CONNECT/tunnel requests get a dedicated relay thread
  - WebSocket upgrades handled transparently
  - Chunked + Content-Length response parsing
  - TCP_NODELAY on all sockets for minimum latency
  - Hop-by-hop headers stripped
  - Windows connectivity check hosts short-circuited
"""
from __future__ import annotations

import select
import socket
import struct
import threading

from .bandwidth import BandwidthManager
from .cache import ResponseCache
from .filters import DomainFilter, IPFilter
from .ftp_handler import handle_ftp_request
from .http_parser import HTTPRequest, parse_request, recv_until
from .logger import get_logger
from .stats import STATS

log = get_logger("proxy.handler")

BUFFER          = 65536
CONNECT_TIMEOUT = 10     # seconds to establish TCP connection to remote
TUNNEL_IDLE     = 300    # seconds idle before tunnel auto-closes (5 min)
READ_TIMEOUT    = 30     # seconds waiting for remote response headers
KEEPALIVE_MAX   = 50     # max requests per keep-alive connection
KEEPALIVE_IDLE  = 30     # seconds idle before closing keep-alive connection

# Headers stripped before forwarding upstream
HOP_BY_HOP = {
    b"proxy-connection", b"proxy-authenticate", b"proxy-authorization",
    b"te", b"trailers", b"transfer-encoding", b"upgrade", b"connection",
}

# Connectivity-check hosts that should be short-circuited immediately
# (they cause delays when they fail DNS or time out)
SHORTCIRCUIT_HOSTS = {
    "ipv6.msftncsi.com",
    "ipv6.msftconnecttest.com",
    "teredo.ipv6.microsoft.com",
}

SOCKS5_VER         = 0x05
SOCKS5_NO_AUTH     = 0x00
SOCKS5_CMD_CONNECT = 0x01
SOCKS5_ATYP_IPV4   = 0x01
SOCKS5_ATYP_DOMAIN = 0x03
SOCKS5_ATYP_IPV6   = 0x04


class ProxyHandler:
    def __init__(self, client_sock, client_addr,
                 ip_filter: IPFilter, domain_filter: DomainFilter,
                 cache: ResponseCache, bandwidth: BandwidthManager):
        self.client        = client_sock
        self.client_ip     = client_addr[0]
        self.ip_filter     = ip_filter
        self.domain_filter = domain_filter
        self.cache         = cache
        self.bandwidth     = bandwidth

    # ── Entry ─────────────────────────────────────────────────────────────────

    def handle(self) -> None:
        STATS.connection_opened()
        try:
            self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client.settimeout(KEEPALIVE_IDLE)

            if not self.ip_filter.is_allowed(self.client_ip):
                log.warning("Blocked IP: %s", self.client_ip)
                STATS.record_request("CONNECT", self.client_ip, 0, "HTTP", "BLOCKED")
                self._send_http_error(403, "Forbidden")
                return

            first = self.client.recv(1, socket.MSG_PEEK)
            if not first:
                return

            if first[0] == SOCKS5_VER:
                self._handle_socks5()
            else:
                self._handle_http_connection()

        except (ConnectionResetError, BrokenPipeError, TimeoutError, OSError):
            pass
        except Exception as exc:
            log.debug("Handler error [%s]: %s", self.client_ip, exc, exc_info=False)
        finally:
            STATS.connection_closed()
            try:
                self.client.close()
            except Exception:
                pass

    # ── HTTP keep-alive loop ──────────────────────────────────────────────────

    def _handle_http_connection(self) -> None:
        """
        Handle an HTTP/1.x connection. Supports keep-alive (pipelining-safe).
        CONNECT requests spin up a relay thread and exit the loop immediately.
        """
        req_count = 0
        while req_count < KEEPALIVE_MAX:
            try:
                self.client.settimeout(KEEPALIVE_IDLE)
                raw = recv_until(self.client)
            except socket.timeout:
                return
            if not raw:
                return

            req = parse_request(raw)
            if req is None:
                self._send_http_error(400, "Bad Request")
                return

            log.info("HTTP %s %s:%d%s [%s]",
                     req.method, req.host, req.port, req.path, self.client_ip)

            # Short-circuit known bad hosts immediately
            if req.host.lower() in SHORTCIRCUIT_HOSTS:
                self._send_http_error(403, "Forbidden")
                req_count += 1
                continue

            if not self.domain_filter.is_allowed(req.host):
                log.warning("Blocked domain: %s [%s]", req.host, self.client_ip)
                STATS.record_request(req.method, req.host, req.port, "HTTP", "BLOCKED")
                self._send_http_error(403, "Forbidden – domain blocked")
                req_count += 1
                continue

            if req.target.lower().startswith("ftp://"):
                ftp_port = req.port if req.port != 80 else 21
                handle_ftp_request(self.client, req.host, ftp_port, req.path)
                STATS.record_request(req.method, req.host, ftp_port, "FTP", "OK")
                return

            if req.is_connect:
                # CONNECT: open tunnel in a relay thread, free this worker
                self._spawn_tunnel(req.host, req.port, "HTTPS")
                return

            if self._is_websocket_upgrade(req):
                self._spawn_websocket_tunnel(req, raw)
                return

            # Plain HTTP request
            keep_alive = self._should_keep_alive(req)
            success    = self._handle_plain_http(req, raw)
            req_count += 1
            if not success or not keep_alive:
                return

    # ── Tunnel spawning (frees worker thread) ─────────────────────────────────

    def _spawn_tunnel(self, host: str, port: int, proto: str) -> None:
        """
        Open remote connection, send 200, then relay in a dedicated thread.
        The worker thread returns immediately after spawning.
        """
        try:
            remote = self._connect_remote(host, port)
        except OSError as exc:
            log.error("CONNECT failed %s:%d – %s", host, port, exc)
            STATS.record_request("CONNECT", host, port, proto, "ERROR")
            self._send_http_error(502, "Bad Gateway")
            return

        # Send 200 before handing off
        try:
            self.client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        except OSError:
            remote.close()
            return

        log.info("CONNECT tunnel %s:%d [%s]", host, port, self.client_ip)
        STATS.record_request("CONNECT", host, port, proto, "OK")

        # Relay thread — completely independent, owns both sockets
        client_sock = self.client
        def _relay():
            try:
                _tunnel_sockets(client_sock, remote, TUNNEL_IDLE)
            finally:
                try: client_sock.close()
                except Exception: pass
                try: remote.close()
                except Exception: pass
                STATS.connection_closed()

        # Account for the extra connection
        STATS.connection_opened()
        t = threading.Thread(target=_relay, daemon=True,
                             name=f"tunnel-{host}")
        t.start()
        # Prevent our handle() from closing the socket on exit
        self.client = _NullSocket()

    def _spawn_websocket_tunnel(self, req: HTTPRequest, raw: bytes) -> None:
        """Forward WebSocket upgrade then tunnel."""
        try:
            remote = self._connect_remote(req.host, req.port)
        except OSError as exc:
            log.error("WS connect failed %s:%d – %s", req.host, req.port, exc)
            self._send_http_error(502, "Bad Gateway")
            return

        try:
            rewritten = self._rewrite_request(raw, req)
            remote.sendall(rewritten)
            resp = self._recv_until_headers(remote)
            if resp:
                self.client.sendall(resp)
        except OSError:
            remote.close()
            return

        log.info("WS tunnel %s:%d [%s]", req.host, req.port, self.client_ip)
        STATS.record_request("GET", req.host, req.port, "WS", "OK")

        client_sock = self.client
        def _relay():
            try:
                _tunnel_sockets(client_sock, remote, TUNNEL_IDLE)
            finally:
                try: client_sock.close()
                except Exception: pass
                try: remote.close()
                except Exception: pass
                STATS.connection_closed()

        STATS.connection_opened()
        threading.Thread(target=_relay, daemon=True,
                         name=f"ws-{req.host}").start()
        self.client = _NullSocket()

    # ── Plain HTTP ────────────────────────────────────────────────────────────

    def _handle_plain_http(self, req: HTTPRequest, raw: bytes) -> bool:
        cache_key = req.cache_key
        cached    = self.cache.get(cache_key) if req.method.upper() == "GET" else None

        if cached:
            response = (cached.status_line + b"\r\n" +
                        cached.headers + b"\r\n\r\n" + cached.body)
            self.bandwidth.throttled_send(self.client, response, self.client_ip)
            STATS.record_cache_hit()
            STATS.record_request(req.method, req.host, req.port, "HTTP", "OK", len(response))
            return True

        try:
            remote = self._connect_remote(req.host, req.port)
        except OSError as exc:
            log.error("Cannot reach %s:%d – %s", req.host, req.port, exc)
            STATS.record_request(req.method, req.host, req.port, "HTTP", "ERROR")
            self._send_http_error(502, "Bad Gateway")
            return False

        try:
            remote.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            cleaned = self._strip_hop_by_hop(self._rewrite_request(raw, req))
            remote.sendall(cleaned)
            response_raw = self._recv_http_response(remote)
            if response_raw:
                self.bandwidth.throttled_send(self.client, response_raw, self.client_ip)
                STATS.record_request(req.method, req.host, req.port,
                                      "HTTP", "OK", len(response_raw))
                if req.method.upper() == "GET":
                    self._cache_response(cache_key, response_raw)
            return True
        finally:
            remote.close()

    # ── SOCKS5 ────────────────────────────────────────────────────────────────

    def _handle_socks5(self) -> None:
        header = self._recv_exact(2)
        if not header or header[0] != SOCKS5_VER:
            return
        self._recv_exact(header[1])
        self.client.sendall(bytes([SOCKS5_VER, SOCKS5_NO_AUTH]))

        req_hdr = self._recv_exact(4)
        if not req_hdr or req_hdr[1] != SOCKS5_CMD_CONNECT:
            self.client.sendall(b"\x05\x07\x00\x01" + b"\x00" * 6)
            return

        atyp = req_hdr[3]
        if atyp == SOCKS5_ATYP_IPV4:
            host = socket.inet_ntoa(self._recv_exact(4))
        elif atyp == SOCKS5_ATYP_DOMAIN:
            host = self._recv_exact(self._recv_exact(1)[0]).decode()
        elif atyp == SOCKS5_ATYP_IPV6:
            host = socket.inet_ntop(socket.AF_INET6, self._recv_exact(16))
        else:
            return

        port = struct.unpack("!H", self._recv_exact(2))[0]
        log.info("SOCKS5 %s:%d [%s]", host, port, self.client_ip)

        if not self.domain_filter.is_allowed(host):
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

        self.client.sendall(
            b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
        STATS.record_request("CONNECT", host, port, "SOCKS5", "OK")

        client_sock = self.client
        def _relay():
            try:
                _tunnel_sockets(client_sock, remote, TUNNEL_IDLE)
            finally:
                try: client_sock.close()
                except Exception: pass
                try: remote.close()
                except Exception: pass
                STATS.connection_closed()

        STATS.connection_opened()
        threading.Thread(target=_relay, daemon=True,
                         name=f"socks5-{host}").start()
        self.client = _NullSocket()

    # ── Socket helpers ────────────────────────────────────────────────────────

    def _connect_remote(self, host: str, port: int) -> socket.socket:
        sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return sock

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.client.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Client disconnected")
            buf += chunk
        return buf

    def _recv_until_headers(self, sock: socket.socket) -> bytes:
        buf = b""
        sock.settimeout(READ_TIMEOUT)
        while b"\r\n\r\n" not in buf and len(buf) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        return buf

    def _recv_http_response(self, sock: socket.socket) -> bytes:
        sock.settimeout(READ_TIMEOUT)
        hbuf = b""
        while b"\r\n\r\n" not in hbuf:
            chunk = sock.recv(4096)
            if not chunk:
                return hbuf
            hbuf += chunk
            if len(hbuf) > 1048576:
                break

        sep      = hbuf.find(b"\r\n\r\n")
        hsec     = hbuf[:sep + 4]
        body_buf = hbuf[sep + 4:]
        hl       = hsec.lower()

        if b"transfer-encoding: chunked" in hl:
            return hsec + self._recv_chunked(sock, body_buf)

        cl_pos = hl.find(b"content-length:")
        if cl_pos != -1:
            cl_end = hl.find(b"\r\n", cl_pos)
            try:
                cl = int(hl[cl_pos+15:cl_end].strip())
                body = body_buf
                while len(body) < cl:
                    d = sock.recv(min(BUFFER, cl - len(body)))
                    if not d:
                        break
                    body += d
                return hsec + body
            except ValueError:
                pass

        if b"101 " in hsec[:20]:
            return hsec + body_buf

        body = body_buf
        sock.settimeout(10)
        try:
            while True:
                d = sock.recv(BUFFER)
                if not d:
                    break
                body += d
        except socket.timeout:
            pass
        return hsec + body

    def _recv_chunked(self, sock: socket.socket, initial: bytes) -> bytes:
        buf  = initial
        body = b""
        sock.settimeout(READ_TIMEOUT)
        while True:
            while b"\r\n" not in buf:
                d = sock.recv(4096)
                if not d:
                    return body + buf
                buf += d
            crlf = buf.find(b"\r\n")
            try:
                chunk_size = int(buf[:crlf].split(b";")[0].strip(), 16)
            except ValueError:
                return body + buf
            buf = buf[crlf + 2:]
            if chunk_size == 0:
                return body
            while len(buf) < chunk_size + 2:
                d = sock.recv(BUFFER)
                if not d:
                    return body + buf
                buf += d
            body += buf[:chunk_size]
            buf   = buf[chunk_size + 2:]

    def _is_websocket_upgrade(self, req: HTTPRequest) -> bool:
        return ("websocket" in req.headers.get("upgrade","").lower() or
                "upgrade"  in req.headers.get("connection","").lower())

    def _should_keep_alive(self, req: HTTPRequest) -> bool:
        conn = req.headers.get("connection","").lower()
        return ("close" not in conn) if req.version == "HTTP/1.1" else ("keep-alive" in conn)

    def _strip_hop_by_hop(self, raw: bytes) -> bytes:
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            return raw
        lines = raw[:sep].split(b"\r\n")
        kept  = [lines[0]]
        for line in lines[1:]:
            if b":" in line:
                name = line.split(b":", 1)[0].strip().lower()
                if name in HOP_BY_HOP:
                    continue
            kept.append(line)
        return b"\r\n".join(kept) + raw[sep:]

    def _rewrite_request(self, raw: bytes, req: HTTPRequest) -> bytes:
        if not (req.target.startswith("http://") or req.target.startswith("https://")):
            return raw
        old = f"{req.method} {req.target} {req.version}".encode()
        new = f"{req.method} {req.path} {req.version}".encode()
        return raw.replace(old, new, 1)

    def _send_http_error(self, code: int, msg: str) -> None:
        body = f"<h1>{code} {msg}</h1>".encode()
        try:
            self.client.sendall(
                f"HTTP/1.1 {code} {msg}\r\nContent-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                .encode() + body)
        except OSError:
            pass

    def _cache_response(self, key: str, raw: bytes) -> None:
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            return
        lines = raw[:sep].split(b"\r\n")
        self.cache.put(key, lines[0], b"\r\n".join(lines[1:]), raw[sep+4:])


# ── Free function: tunnel two sockets ────────────────────────────────────────

def _tunnel_sockets(a: socket.socket, b: socket.socket,
                    idle_timeout: int) -> None:
    """Relay bytes between two sockets until one closes or idle timeout."""
    a.settimeout(None)
    b.settimeout(None)
    while True:
        try:
            r, _, _ = select.select([a, b], [], [], idle_timeout)
        except Exception:
            break
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


# ── Null socket: used after ownership transferred to relay thread ─────────────

class _NullSocket:
    """Drop-in for socket after ownership is handed to a relay thread."""
    def close(self):        pass
    def sendall(self, _):   pass
    def recv(self, _):      return b""
    def setsockopt(self, *a): pass
    def settimeout(self, _): pass