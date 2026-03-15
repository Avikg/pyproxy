"""
ftp_handler.py – FTP-over-HTTP: translate ftp:// requests into real FTP downloads.

Clients send:  GET ftp://ftp.example.com/pub/file.txt HTTP/1.1
We respond with the file content wrapped in an HTTP 200 response.
"""
from __future__ import annotations

import ftplib
import io
import mimetypes
import os
import socket

from .logger import get_logger

log = get_logger("proxy.ftp")

DEFAULT_FTP_PORT = 21
ANONYMOUS = ("anonymous", "proxy@localhost")


def handle_ftp_request(client_sock: socket.socket, host: str, port: int, path: str) -> bool:
    """
    Download path from ftp://host:port/path and stream it back to client_sock
    as an HTTP response.

    Returns True if handled successfully, False if the caller should fall through.
    """
    log.info("FTP GET ftp://%s:%d%s", host, port, path)

    buf = io.BytesIO()
    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=30)
        ftp.login(*ANONYMOUS)
        ftp.retrbinary(f"RETR {path}", buf.write)
        ftp.quit()
    except ftplib.all_errors as exc:
        log.error("FTP error %s:%d%s – %s", host, port, path, exc)
        _send_error(client_sock, 502, f"FTP error: {exc}")
        return True

    data = buf.getvalue()
    mime, _ = mimetypes.guess_type(os.path.basename(path))
    content_type = mime or "application/octet-stream"

    header = (
        f"HTTP/1.1 200 OK\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(data)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode()

    try:
        client_sock.sendall(header + data)
    except OSError:
        pass
    return True


def _send_error(sock: socket.socket, code: int, msg: str) -> None:
    body = f"<h1>{code} {msg}</h1>".encode()
    resp = (
        f"HTTP/1.1 {code} Error\r\n"
        f"Content-Type: text/html\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body
    try:
        sock.sendall(resp)
    except OSError:
        pass
