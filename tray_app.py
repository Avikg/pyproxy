"""
tray_app.py – PyProxy system tray app (no GUI window).
Right-click tray icon for controls.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_PATH = BASE_DIR / "config.yaml"
LOG_PATH    = BASE_DIR / "proxy.log"

DEFAULT_CONFIG = """\
server:
  host: "0.0.0.0"
  port: 8080
  workers: 50

logging:
  level: "INFO"
  log_file: proxy.log
  max_bytes: 10485760
  backup_count: 5

cache:
  enabled: true
  max_size: 256
  ttl: 300

bandwidth:
  enabled: true
  default_kbps: 0
  per_ip: {}

ip_filter:
  mode: "none"
  list: []

domain_filter:
  mode: "none"
  list: []
"""

if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(DEFAULT_CONFIG)

sys.path.insert(0, str(BASE_DIR))

from proxy import ProxyServer, load_config
from proxy.stats import STATS
import pystray
from PIL import Image, ImageDraw


def _make_icon(active: bool) -> Image.Image:
    size = 64
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg   = (34, 197, 94) if active else (107, 114, 128)
    draw.ellipse([4, 4, size-4, size-4], fill=bg)
    draw.rectangle([20, 16, 26, 48], fill="white")
    draw.rectangle([20, 16, 36, 22], fill="white")
    draw.rectangle([20, 30, 36, 36], fill="white")
    draw.ellipse([26, 16, 40, 36], fill=bg)
    draw.ellipse([28, 18, 38, 34], fill="white")
    draw.rectangle([26, 24, 34, 30], fill=bg)
    return img


def _open_file(path: Path):
    """Open a file in the default app (Notepad on Windows)."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


class App:
    def __init__(self):
        self._server = None
        self._thread = None
        self._lock   = threading.Lock()
        self._icon   = None

    # ── Proxy ─────────────────────────────────────────────────────────────────

    def start_proxy(self):
        with self._lock:
            if self._server is not None:
                return
            cfg = load_config(str(CONFIG_PATH))
            cfg.logging.log_file = str(LOG_PATH)
            self._server = ProxyServer(cfg)
        STATS.reset()
        self._thread = threading.Thread(
            target=self._server.start, daemon=True, name="proxy")
        self._thread.start()
        time.sleep(0.4)
        self._refresh()

    def stop_proxy(self):
        with self._lock:
            if self._server is None:
                return
            srv, self._server = self._server, None
        srv.stop()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._refresh()

    def restart_proxy(self):
        self.stop_proxy()
        time.sleep(0.3)
        self.start_proxy()

    @property
    def running(self):
        return self._server is not None

    # ── Tray ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        if not self._icon:
            return
        self._icon.icon  = _make_icon(self.running)
        self._icon.title = f"PyProxy – {'Running' if self.running else 'Stopped'}"
        self._icon.menu  = self._menu()

    def _menu(self):
        try:
            port = load_config(str(CONFIG_PATH)).server.port
        except Exception:
            port = 8080

        snap   = STATS.snapshot()
        status = (f"● Running  127.0.0.1:{port}"
                  if self.running else "○ Stopped")
        info   = (f"Reqs: {snap['total_requests']}  "
                  f"Blocked: {snap['blocked_requests']}  "
                  f"Uptime: {snap['uptime_str']}")

        return pystray.Menu(
            pystray.MenuItem(status, None, enabled=False),
            pystray.MenuItem(info,   None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start",   self._do_start,   enabled=not self.running),
            pystray.MenuItem("Stop",    self._do_stop,    enabled=self.running),
            pystray.MenuItem("Restart", self._do_restart, enabled=self.running),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("View Log",     self._do_open_log),
            pystray.MenuItem("Open Config",  self._do_open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._do_quit),
        )

    # ── Menu actions ──────────────────────────────────────────────────────────

    def _do_start(self, *_):
        threading.Thread(target=self.start_proxy, daemon=True).start()

    def _do_stop(self, *_):
        threading.Thread(target=self.stop_proxy, daemon=True).start()

    def _do_restart(self, *_):
        threading.Thread(target=self.restart_proxy, daemon=True).start()

    def _do_open_log(self, *_):
        if not LOG_PATH.exists():
            LOG_PATH.touch()
        _open_file(LOG_PATH)

    def _do_open_config(self, *_):
        _open_file(CONFIG_PATH)

    def _do_quit(self, *_):
        self.stop_proxy()
        self._icon.stop()

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        threading.Thread(target=self.start_proxy, daemon=True).start()

        self._icon = pystray.Icon(
            name="PyProxy",
            icon=_make_icon(False),
            title="PyProxy – Starting…",
            menu=self._menu(),
        )

        # Refresh stats in tray every 5 seconds
        def _ticker():
            while True:
                time.sleep(5)
                if self._icon:
                    self._refresh()
        threading.Thread(target=_ticker, daemon=True).start()

        self._icon.run()


if __name__ == "__main__":
    App().run()