"""
tray_app.py – System tray entry point for PyProxy.

Runs the proxy server in a background thread and exposes
Start / Stop / Open Config / View Log / Quit via a taskbar icon.
Works on Windows without a terminal window.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# ── Resolve base dir whether running as .exe or .py ──────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_PATH = BASE_DIR / "config.yaml"
LOG_PATH    = BASE_DIR / "proxy.log"

# ── Ensure config.yaml exists next to the exe ────────────────────────────────
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

# ── Patch sys.path so proxy package is found ─────────────────────────────────
sys.path.insert(0, str(BASE_DIR))

from proxy import ProxyServer, load_config  # noqa: E402

import pystray                              # noqa: E402
from PIL import Image, ImageDraw           # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Tray icon image (drawn programmatically – no external asset needed)
# ─────────────────────────────────────────────────────────────────────────────

def _make_icon(active: bool) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circle background
    bg = (34, 197, 94) if active else (107, 114, 128)   # green : grey
    draw.ellipse([4, 4, size - 4, size - 4], fill=bg)

    # "P" letter
    draw.rectangle([20, 16, 26, 48], fill="white")
    draw.rectangle([20, 16, 36, 22], fill="white")
    draw.rectangle([20, 30, 36, 36], fill="white")
    draw.ellipse([26, 16, 40, 36], fill=bg)
    draw.ellipse([28, 18, 38, 34], fill="white")
    draw.rectangle([26, 24, 34, 30], fill=bg)

    return img


# ─────────────────────────────────────────────────────────────────────────────
# Application state
# ─────────────────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self._server: ProxyServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._icon: pystray.Icon | None = None

    # ── Server control ───────────────────────────────────────────────────────

    def _load_server(self) -> ProxyServer:
        cfg = load_config(str(CONFIG_PATH))
        # Always write log next to the exe
        cfg.logging.log_file = str(LOG_PATH)
        return ProxyServer(cfg)

    def start_proxy(self):
        with self._lock:
            if self._server is not None:
                return
            self._server = self._load_server()

        self._thread = threading.Thread(
            target=self._server.start,
            name="proxy-server",
            daemon=True,
        )
        self._thread.start()
        time.sleep(0.3)
        self._refresh_menu()

    def stop_proxy(self):
        with self._lock:
            if self._server is None:
                return
            srv = self._server
            self._server = None

        srv.stop()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        self._refresh_menu()

    @property
    def is_running(self) -> bool:
        return self._server is not None

    # ── Menu actions ─────────────────────────────────────────────────────────

    def action_start(self, icon, item):
        threading.Thread(target=self.start_proxy, daemon=True).start()

    def action_stop(self, icon, item):
        threading.Thread(target=self.stop_proxy, daemon=True).start()

    def action_open_config(self, icon, item):
        if sys.platform == "win32":
            os.startfile(str(CONFIG_PATH))
        else:
            subprocess.Popen(["xdg-open", str(CONFIG_PATH)])

    def action_open_log(self, icon, item):
        if not LOG_PATH.exists():
            LOG_PATH.touch()
        if sys.platform == "win32":
            os.startfile(str(LOG_PATH))
        else:
            subprocess.Popen(["xdg-open", str(LOG_PATH)])

    def action_restart(self, icon, item):
        def _do():
            self.stop_proxy()
            time.sleep(0.5)
            self.start_proxy()
        threading.Thread(target=_do, daemon=True).start()

    def action_quit(self, icon, item):
        self.stop_proxy()
        icon.stop()

    # ── Menu builder ─────────────────────────────────────────────────────────

    def _build_menu(self) -> pystray.Menu:
        running = self.is_running
        cfg = load_config(str(CONFIG_PATH))
        port = cfg.server.port

        status_text = f"● Running on port {port}" if running else "○ Stopped"

        return pystray.Menu(
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start",
                self.action_start,
                enabled=not running,
            ),
            pystray.MenuItem(
                "Stop",
                self.action_stop,
                enabled=running,
            ),
            pystray.MenuItem(
                "Restart",
                self.action_restart,
                enabled=running,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open config.yaml", self.action_open_config),
            pystray.MenuItem("Open proxy.log",   self.action_open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.action_quit),
        )

    def _refresh_menu(self):
        if self._icon:
            self._icon.icon = _make_icon(self.is_running)
            self._icon.menu = self._build_menu()
            title = "PyProxy – Running" if self.is_running else "PyProxy – Stopped"
            self._icon.title = title

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self):
        # Auto-start proxy on launch
        threading.Thread(target=self.start_proxy, daemon=True).start()

        self._icon = pystray.Icon(
            name="PyProxy",
            icon=_make_icon(False),
            title="PyProxy – Starting…",
            menu=self._build_menu(),
        )

        # Refresh icon once proxy has started
        def _delayed_refresh():
            time.sleep(0.8)
            self._refresh_menu()

        threading.Thread(target=_delayed_refresh, daemon=True).start()
        self._icon.run()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().run()
