"""
http_parser.py – Minimal HTTP/1.x request parser (headers only).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class HTTPRequest:
    method: str
    target: str                          # exactly as sent by client
    version: str
    headers: Dict[str, str] = field(default_factory=dict)
    raw_header: bytes = b""

    # Derived
    host: str = ""
    port: int = 80
    path: str = "/"

    @property
    def is_connect(self) -> bool:
        return self.method.upper() == "CONNECT"

    @property
    def cache_key(self) -> str:
        return f"{self.method.upper()}|{self.host}:{self.port}|{self.path}"


_REQUEST_LINE = re.compile(rb"^(\S+)\s+(\S+)\s+(HTTP/\S+)")


def recv_until(sock, delimiter: bytes = b"\r\n\r\n", max_bytes: int = 65536) -> bytes:
    """Read from sock until delimiter is found or max_bytes reached."""
    buf = b""
    while len(buf) < max_bytes:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if delimiter in buf:
            break
    return buf


def parse_request(raw: bytes) -> Optional[HTTPRequest]:
    """
    Parse a raw HTTP request header block.
    Returns an HTTPRequest or None on parse failure.
    """
    header_end = raw.find(b"\r\n\r\n")
    if header_end == -1:
        header_end = len(raw)

    header_block = raw[:header_end]
    lines = header_block.split(b"\r\n")
    if not lines:
        return None

    m = _REQUEST_LINE.match(lines[0])
    if not m:
        return None

    method = m.group(1).decode("latin-1")
    target = m.group(2).decode("latin-1")
    version = m.group(3).decode("latin-1")

    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if b":" in line:
            k, _, v = line.partition(b":")
            headers[k.strip().lower().decode("latin-1")] = v.strip().decode("latin-1")

    req = HTTPRequest(
        method=method,
        target=target,
        version=version,
        headers=headers,
        raw_header=raw[:header_end + 4],
    )

    req.host, req.port, req.path = _extract_host_port_path(req)
    return req


def _extract_host_port_path(req: HTTPRequest) -> Tuple[str, int, str]:
    """Derive (host, port, path) from the request target + Host header."""
    target = req.target

    if req.is_connect:
        # CONNECT host:port
        host, _, port_str = target.rpartition(":")
        return host, int(port_str) if port_str.isdigit() else 443, "/"

    if target.startswith("http://") or target.startswith("https://"):
        # Absolute-form
        scheme, _, rest = target.partition("://")
        default_port = 443 if scheme == "https" else 80
        authority, _, path = rest.partition("/")
        path = "/" + path
        if ":" in authority:
            host, _, port_str = authority.rpartition(":")
            port = int(port_str) if port_str.isdigit() else default_port
        else:
            host, port = authority, default_port
        return host, port, path

    # Origin-form – fall back to Host header
    host_header = req.headers.get("host", "")
    if ":" in host_header:
        host, _, port_str = host_header.rpartition(":")
        port = int(port_str) if port_str.isdigit() else 80
    else:
        host, port = host_header, 80

    return host, port, target
