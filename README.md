# PyProxy

A CCProxy-style multi-protocol internet proxy server written in Python.
Runs as a **system tray application** — no terminal, no VS Code needed.

## Features

| Feature | Details |
|---|---|
| **Protocols** | HTTP, HTTPS (CONNECT tunnel), SOCKS5, FTP-over-HTTP |
| **System tray** | Start / Stop / Restart / Open config / View log |
| **IP filter** | None / allowlist / blocklist (CIDR ranges supported) |
| **Domain filter** | None / allowlist / blocklist (`*.wildcard` patterns) |
| **Web cache** | In-memory LRU cache for HTTP GET responses |
| **Bandwidth control** | Token-bucket throttler per client IP |
| **Logging** | Console + rotating log file |

---

## Building the Standalone .exe (Windows)

Requirements: **Python 3.10+** installed and on PATH.

```bat
build.bat
```

That's it. The script will:
1. Create a `.venv`
2. Install all dependencies
3. Run PyInstaller
4. Output `dist\PyProxy.exe`

### Distributing to other machines

Copy the `dist\` folder — it contains:
```
dist\
├── PyProxy.exe       ← double-click to run
└── config.yaml       ← edit to change settings
```

No Python installation required on the target machine.

---

## Usage

1. Double-click `PyProxy.exe`
2. A **green circle icon** appears in the system tray (bottom-right taskbar)
3. Right-click the icon for options:
   - **Start / Stop / Restart** the proxy
   - **Open config.yaml** — edit settings (restart to apply)
   - **Open proxy.log** — view live logs

---

## Windows Proxy Setup

After starting PyProxy, point Windows at it:

1. **Settings → Network & Internet → Proxy**
2. Enable **"Use a proxy server"**
3. Address: `127.0.0.1` · Port: `8080`
4. Click **Save**

All browser traffic will now route through PyProxy.

---

## config.yaml Reference

```yaml
server:
  host: "0.0.0.0"
  port: 8080          # change port here
  workers: 50

logging:
  level: "INFO"       # DEBUG | INFO | WARNING | ERROR
  log_file: proxy.log
  max_bytes: 10485760
  backup_count: 5

cache:
  enabled: true
  max_size: 256
  ttl: 300            # seconds

bandwidth:
  enabled: true
  default_kbps: 0     # 0 = unlimited
  per_ip:
    "192.168.1.50": 512   # throttle one IP to 512 KB/s

ip_filter:
  mode: "none"        # none | allowlist | blocklist
  list: []

domain_filter:
  mode: "none"        # none | allowlist | blocklist
  list:
    - "*.ads.com"
    - "tracker.net"
```

---

## Running from source (development)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python tray_app.py       # tray mode
python main.py           # CLI mode
```

---

## Project Structure

```
pyproxy/
├── tray_app.py           ← tray GUI entry point
├── main.py               ← CLI entry point
├── build.bat             ← one-click Windows build script
├── pyproxy.spec          ← PyInstaller spec
├── config.yaml           ← default configuration
├── requirements.txt
└── proxy/
    ├── config.py         ← config loader
    ├── logger.py         ← rotating log setup
    ├── filters.py        ← IP & domain filtering
    ├── cache.py          ← LRU response cache
    ├── bandwidth.py      ← token-bucket throttler
    ├── http_parser.py    ← HTTP/1.x parser
    ├── ftp_handler.py    ← FTP-over-HTTP
    ├── handler.py        ← per-connection dispatcher
    └── server.py         ← thread-pool TCP server
```