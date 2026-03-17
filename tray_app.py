"""
tray_app.py – Avik Proxy system tray app.
Uses avik_proxy.ico for the tray icon if available,
falls back to a generated icon.
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
ICON_PATH   = BASE_DIR / "avik_proxy.ico"
PNG_PATH    = BASE_DIR / "avik_proxy.png"

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
import math


def _load_icon(active: bool) -> Image.Image:
    """Load avik_proxy icon from file, tinting green/grey for active state."""
    source = PNG_PATH if PNG_PATH.exists() else (ICON_PATH if ICON_PATH.exists() else None)
    if source:
        try:
            img = Image.open(source).convert("RGBA").resize((64, 64), Image.LANCZOS)
            if not active:
                # Desaturate to grey when stopped
                import PIL.ImageEnhance as IE
                img = IE.Color(img).enhance(0.0)
            return img
        except Exception:
            pass
    return _generated_icon(active)


def _generated_icon(active: bool) -> Image.Image:
    """Fallback generated icon."""
    size = 64
    img  = Image.new("RGBA", (size, size), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    cx, cy = size//2, size//2

    draw.ellipse([2,2,size-2,size-2], fill=(26,26,46,255))

    r_ring = size//2 - 6
    draw.ellipse([cx-r_ring,cy-r_ring,cx+r_ring,cy+r_ring],
                 outline=(124,58,237,100), width=2)

    r_dot = int(size * 0.40)
    colors = [(34,197,94),(124,58,237),(59,130,246)]
    for i in range(6):
        rad = math.radians(i * 60 - 90)
        dx  = int(cx + r_dot * math.cos(rad))
        dy  = int(cy + r_dot * math.sin(rad))
        col = colors[i % 3]
        draw.line([(cx,cy),(dx,dy)], fill=col+(50,), width=1)
        draw.ellipse([dx-3,dy-3,dx+3,dy+3], fill=col+(200,))

    sh  = int(size * 0.27)
    pts = [(cx + sh*math.cos(math.radians(i*60-30)),
            cy + sh*math.sin(math.radians(i*60-30))) for i in range(6)]
    bg  = (34,197,94,220) if active else (80,80,100,200)
    draw.polygon(pts, fill=bg, outline=(255,255,255,180))

    fw, fh = 5, 11
    ox, oy = cx - fw*2, cy - fh//2
    draw.polygon([(ox,oy+fh),(ox+fw,oy+fh),(cx,oy),(cx-fw//2,oy)],
                 fill=(255,255,255,255))
    draw.polygon([(cx+fw//2,oy),(cx,oy),(ox+fw*4,oy+fh),(ox+fw*3,oy+fh)],
                 fill=(255,255,255,255))
    draw.rectangle([ox+fw+1, oy+fh//2, ox+fw*3-1, oy+fh//2+3],
                   fill=(255,255,255,255))
    return img


def _open_file(path: Path):
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

    def _refresh(self):
        if not self._icon:
            return
        self._icon.icon  = _load_icon(self.running)
        self._icon.title = f"Avik Proxy – {'Running' if self.running else 'Stopped'}"
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
            pystray.MenuItem("Avik Proxy",  None, enabled=False),
            pystray.MenuItem(status,         None, enabled=False),
            pystray.MenuItem(info,           None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start",   self._do_start,   enabled=not self.running),
            pystray.MenuItem("Stop",    self._do_stop,    enabled=self.running),
            pystray.MenuItem("Restart", self._do_restart, enabled=self.running),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("View Log",    self._do_open_log),
            pystray.MenuItem("Open Config", self._do_open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._do_quit),
        )

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

    def run(self):
        threading.Thread(target=self.start_proxy, daemon=True).start()

        self._icon = pystray.Icon(
            name="AvikProxy",
            icon=_load_icon(False),
            title="Avik Proxy – Starting…",
            menu=self._menu(),
        )

        def _ticker():
            while True:
                time.sleep(5)
                if self._icon:
                    self._refresh()
        threading.Thread(target=_ticker, daemon=True).start()

        self._icon.run()


if __name__ == "__main__":
    App().run()
