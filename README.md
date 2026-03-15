# PyProxy

A CCProxy-style multi-protocol internet proxy server written in Python.
Runs silently as a **system tray application** — no terminal, no console window.
Distributable to any Windows machine via a standard installer.

---

## Table of Contents

1. [Features](#features)
2. [How It Works](#how-it-works)
3. [Project Structure](#project-structure)
4. [Requirements](#requirements)
5. [Running from Source](#running-from-source)
6. [Building the Installer](#building-the-installer)
7. [Installing on Another Machine](#installing-on-another-machine)
8. [Windows Proxy Setup](#windows-proxy-setup)
9. [SOCKS5 Setup](#socks5-setup)
10. [System Tray Usage](#system-tray-usage)
11. [Configuration Reference](#configuration-reference)
12. [CLI Reference](#cli-reference)
13. [Blocking IPs and Domains](#blocking-ips-and-domains)
14. [Viewing Logs](#viewing-logs)
15. [Running Tests](#running-tests)
16. [Troubleshooting](#troubleshooting)

---

## Features

| Feature | Details |
|---|---|
| **HTTP proxy** | Full HTTP/1.x forwarding with URL rewriting |
| **HTTPS proxy** | CONNECT tunnel — TLS handled end-to-end by client |
| **SOCKS5 proxy** | IPv4, IPv6, and domain name addressing |
| **FTP-over-HTTP** | Translates `ftp://` requests into real FTP downloads |
| **Web cache** | In-memory LRU cache for HTTP GET responses |
| **IP filtering** | Allow or block client IPs by address or CIDR range |
| **Domain filtering** | Allow or block destinations by hostname or `*.wildcard` |
| **Bandwidth control** | Per-IP token-bucket throttler (KB/s) |
| **System tray** | Green/grey icon with live stats, no window needed |
| **Rotating log** | Console + rotating file log |
| **Installer** | Inno Setup `.exe` installer — no antivirus false positives |

---

## How It Works

```
Client (browser / app)
        │
        │  HTTP  HTTPS(CONNECT)  SOCKS5  FTP-over-HTTP
        ▼
┌─────────────────────┐
│  TCP Server         │  Listens on 0.0.0.0:8080
│  (Thread Pool x50)  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  IP Filter          │  Block/allow by client IP or CIDR
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Protocol Detect    │  SOCKS5 (0x05) vs HTTP/FTP
└──────┬──────────────┘
       │
  ┌────┴──────────────────────────────┐
  │                                   │
  ▼                                   ▼
SOCKS5 Handler                  HTTP Parser
  │                                   │
  │                         ┌─────────┴──────────┐
  │                         │                    │
  │                    Domain Filter        FTP-over-HTTP
  │                         │
  │                  ┌──────┴─────────┐
  │                  │                │
  │             Cache Lookup     CONNECT Tunnel
  │                  │
  ▼                  ▼
┌──────────────────────────────┐
│  Bandwidth Throttler         │  Token bucket per client IP
└──────────────────────────────┘
         │
         ▼
   Remote Server (internet)
```

| Protocol | Behaviour |
|---|---|
| **HTTP** | Request forwarded; response cached for GET requests |
| **HTTPS** | `CONNECT` tunnel opened; proxy relays raw bytes, TLS is client-side |
| **SOCKS5** | Full RFC 1928 CONNECT; IPv4 / IPv6 / domain all supported |
| **FTP-over-HTTP** | `GET ftp://host/path` → real FTP download → HTTP 200 response |

---

## Project Structure

```
pyproxy/
│
├── tray_app.py              System tray entry point (run this)
├── main.py                  CLI / headless entry point
│
├── build_installer.bat      One-click installer build script
├── pyproxy_installer.iss    Inno Setup installer configuration
├── requirements.txt         All dependencies (dev + runtime)
├── requirements_runtime.txt Runtime-only dependencies for installer
│
├── config.yaml              Configuration file (edit to change settings)
│
└── proxy/                   Core proxy package
    ├── __init__.py          Exports ProxyServer, load_config
    ├── server.py            Thread-pool TCP server
    ├── handler.py           Per-connection dispatcher
    ├── http_parser.py       HTTP/1.x request parser
    ├── ftp_handler.py       FTP-over-HTTP translator
    ├── filters.py           IP and domain allow/blocklist
    ├── cache.py             Thread-safe LRU response cache
    ├── bandwidth.py         Token-bucket bandwidth throttler
    ├── stats.py             Live metrics collector
    ├── config.py            Config dataclasses and YAML loader
    └── logger.py            Rotating log setup
```

---

## Requirements

### On your development / build machine
- Python **3.10 or newer** — https://python.org/downloads
- Inno Setup 6 (for building the installer) — https://jrsoftware.org/isdl.php
- Windows 10 / 11

### On the target machine (where proxy will run)
- Python **3.10 or newer** — https://python.org/downloads
- Windows 10 / 11
- No VS Code, no terminal, no other tools needed

---

## Running from Source

Use this during development — changes take effect immediately, no rebuild needed.

### Step 1 — Clone or download the project

```
C:\Development\pyproxy\
├── tray_app.py
├── main.py
├── config.yaml
├── requirements.txt
└── proxy\
```

### Step 2 — Create virtual environment

```powershell
cd C:\Development\pyproxy
python -m venv .venv
```

### Step 3 — Activate virtual environment

```powershell
# PowerShell
.venv\Scripts\Activate.ps1

# CMD
.venv\Scripts\activate.bat
```

### Step 4 — Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 5 — Run

```powershell
# Tray mode (recommended — runs silently in system tray)
python tray_app.py

# CLI / headless mode (shows logs in terminal)
python main.py
```

A **green P icon** appears in the system tray (bottom-right taskbar).
Right-click it to control the proxy.

---

## Building the Installer

This produces `PyProxySetup.exe` — a standard Windows installer you can
send to any machine. It does **not** use PyInstaller, so antivirus will
never flag it.

### Prerequisites

1. Install **Inno Setup 6** from https://jrsoftware.org/isdl.php
2. Make sure Python and your `.venv` are set up (see above)

### Build

```powershell
cd C:\Development\pyproxy
.\build_installer.bat
```

The script automatically:
1. Activates the virtual environment
2. Installs/updates dependencies
3. Runs Inno Setup compiler
4. Outputs `installer_output\PyProxySetup.exe`

### Output

```
installer_output\
└── PyProxySetup.exe    ← send this file to the target machine
```

---

## Installing on Another Machine

### Requirements on target machine
- Windows 10 or 11
- Python 3.10+ installed from https://python.org/downloads
  - During Python install, tick **"Add Python to PATH"**

### Installation steps

1. Copy `PyProxySetup.exe` to the target machine (USB, email, Google Drive, etc.)
2. Double-click `PyProxySetup.exe`
3. The installer wizard opens:

```
[Welcome]
  → Click Next

[Select Destination]
  → Default: C:\Users\<you>\AppData\Local\PyProxy
  → Click Next

[Select Additional Tasks]
  ☐ Create a desktop shortcut    (optional)
  ☐ Start PyProxy when Windows starts  (optional — recommended)
  → Click Next

[Ready to Install]
  → Click Install

[Installing...]
  → Automatically runs: pip install pystray Pillow PyYAML

[Finish]
  ☑ Launch PyProxy now
  → Click Finish
```

4. A **green P icon** appears in the system tray — proxy is running.

### What gets installed

```
C:\Users\<you>\AppData\Local\PyProxy\
├── tray_app.py          Main script
├── main.py              CLI script
├── start.vbs            Silent launcher (used by shortcuts)
├── config.yaml          Configuration (edit this to change settings)
├── requirements_runtime.txt
└── proxy\               Core proxy package
    └── (all .py files)
```

Start Menu entries:
- **PyProxy** — starts the proxy
- **Uninstall PyProxy** — removes everything

### Uninstalling

- **Settings → Apps → PyProxy → Uninstall**
- or: **Start Menu → PyProxy → Uninstall PyProxy**

---

## Windows Proxy Setup

After PyProxy is running, configure Windows to use it:

1. Open **Settings → Network & Internet → Proxy**
2. Under *Manual proxy setup* click **Set up**
3. Toggle **"Use a proxy server"** → **On**
4. Address: `127.0.0.1`
5. Port: `8080`
6. Click **Save**

All HTTP and HTTPS traffic from browsers and most Windows apps will
now route through PyProxy.

To verify: right-click the tray icon — it should show
`● Running  127.0.0.1:8080` and the request count should increase as
you browse.

---

## SOCKS5 Setup

SOCKS5 runs on the **same port** as HTTP (8080 by default).

### Firefox

1. **Options → General → Network Settings → Manual proxy configuration**
2. SOCKS Host: `127.0.0.1`   Port: `8080`
3. Select **SOCKS v5**
4. Check **"Proxy DNS when using SOCKS v5"**
5. Click **OK**

### Chrome / Edge (via command line)

```powershell
chrome.exe --proxy-server="socks5://127.0.0.1:8080"
```

### curl

```powershell
curl.exe --socks5 127.0.0.1:8080 https://example.com
```

### Python test

```powershell
python -c "import urllib.request; h=urllib.request.ProxyHandler({'http':'http://127.0.0.1:8080'}); o=urllib.request.build_opener(h); print(o.open('http://example.com').read(100))"
```

---

## System Tray Usage

PyProxy lives in the **system tray** (bottom-right corner of taskbar).
If you don't see it, click the **`^`** arrow to show hidden icons.

### Icon colours

| Icon | Meaning |
|---|---|
| 🟢 Green circle with P | Proxy is running |
| ⚫ Grey circle with P | Proxy is stopped |

### Right-click menu

```
● Running  127.0.0.1:8080          ← status (not clickable)
Reqs: 42  Blocked: 1  Uptime: 5m   ← live stats (updates every 5s)
─────────────────────────────
Start                               ← greyed out when running
Stop
Restart
─────────────────────────────
View Log                            ← opens proxy.log in Notepad
Open Config                         ← opens config.yaml in Notepad
─────────────────────────────
Quit                                ← stops proxy and exits tray
```

### Applying config changes

1. Right-click tray → **Open Config**
2. Edit `config.yaml` and save
3. Right-click tray → **Restart**

Changes take effect immediately after restart.

---

## Configuration Reference

`config.yaml` lives next to the installed scripts.
All changes require a **Restart** to take effect.

```yaml
# ── Server ────────────────────────────────────────────────────────────────────
server:
  host: "0.0.0.0"       # Bind address. Use 127.0.0.1 for localhost only.
  port: 8080            # Port for HTTP, HTTPS, SOCKS5 and FTP-over-HTTP.
  workers: 50           # Max simultaneous connections (thread pool size).

# ── Logging ───────────────────────────────────────────────────────────────────
logging:
  level: "INFO"         # DEBUG | INFO | WARNING | ERROR
  log_file: proxy.log   # Log file path (relative = next to config.yaml).
  max_bytes: 10485760   # Max size per log file: 10 MB.
  backup_count: 5       # Number of rotated log files to keep.

# ── Web Cache ─────────────────────────────────────────────────────────────────
cache:
  enabled: true         # Set false to disable caching entirely.
  max_size: 256         # Max number of responses stored in memory.
  ttl: 300              # Seconds before a cached response expires.

# ── Bandwidth Control ─────────────────────────────────────────────────────────
bandwidth:
  enabled: true         # Set false to disable throttling entirely.
  default_kbps: 0       # Speed cap for all clients. 0 = unlimited.
  per_ip:               # Per-client overrides (KB/s).
    "192.168.1.50": 512
    "192.168.1.51": 1024

# ── IP Filter ─────────────────────────────────────────────────────────────────
ip_filter:
  mode: "none"          # none | allowlist | blocklist
  list:
    - "192.168.1.100"   # exact IP
    - "10.0.0.0/8"      # CIDR range

# ── Domain Filter ─────────────────────────────────────────────────────────────
domain_filter:
  mode: "none"          # none | allowlist | blocklist
  list:
    - "ads.example.com"
    - "*.tracker.net"   # wildcard — matches any subdomain
```

### Important rules

- **Always use `list: []`** for empty lists — never leave it blank or commented,
  this causes a startup crash.
- **Always use `per_ip: {}`** for empty bandwidth rules.
- CIDR notation (`10.0.0.0/8`, `192.168.0.0/24`) is supported in `ip_filter`.
- Wildcards (`*.ads.com`) match subdomains but NOT the bare domain `ads.com`.

---

## CLI Reference

`main.py` provides headless mode — logs print to the terminal.
All flags override `config.yaml`.

```powershell
python main.py [OPTIONS]
```

| Flag | Description | Example |
|---|---|---|
| `--config PATH` | Use a custom config file | `--config D:\proxy.yaml` |
| `--host HOST` | Override bind address | `--host 127.0.0.1` |
| `--port PORT` | Override listen port | `--port 9090` |
| `--workers N` | Override thread pool size | `--workers 100` |
| `--log-level LEVEL` | Override log verbosity | `--log-level DEBUG` |

### Examples

```powershell
# Start with defaults
python main.py

# Debug mode on a custom port
python main.py --port 9090 --log-level DEBUG

# Localhost only
python main.py --host 127.0.0.1

# Custom config file
python main.py --config C:\Users\me\myproxy.yaml
```

---

## Blocking IPs and Domains

### Block a specific IP

Edit `config.yaml`:
```yaml
ip_filter:
  mode: "blocklist"
  list:
    - "192.168.1.55"
```
Save → Restart proxy.

### Block an IP range (CIDR)

```yaml
ip_filter:
  mode: "blocklist"
  list:
    - "10.0.0.0/8"
    - "192.168.1.0/24"
```

### Allow only specific IPs (whitelist mode)

```yaml
ip_filter:
  mode: "allowlist"
  list:
    - "192.168.1.10"
    - "192.168.1.11"
```

### Block a website / domain

```yaml
domain_filter:
  mode: "blocklist"
  list:
    - "ads.example.com"
    - "*.doubleclick.net"
    - "malware.com"
```

### Allow only specific websites

```yaml
domain_filter:
  mode: "allowlist"
  list:
    - "google.com"
    - "*.google.com"
    - "github.com"
```

### Apply changes

Right-click tray icon → **Restart**

Blocked requests show `BLOCKED` status in the log with HTTP 403 response
to the client.

---

## Viewing Logs

### From the tray

Right-click tray icon → **View Log** — opens `proxy.log` in Notepad.

### Log file location

| Mode | Location |
|---|---|
| Running from source | `C:\Development\pyproxy\proxy.log` |
| Installed via installer | `C:\Users\<you>\AppData\Local\PyProxy\proxy.log` |

### Log format

```
2026-03-16 08:31:01 [INFO]  worker-3 – HTTP GET example.com:80/index.html [192.168.1.5]
2026-03-16 08:31:02 [INFO]  worker-1 – CONNECT tunnel google.com:443 [192.168.1.5]
2026-03-16 08:31:03 [WARNING] worker-2 – Blocked domain: ads.tracker.net [192.168.1.5]
```

### Log levels

| Level | What you see |
|---|---|
| `ERROR` | Only failures and crashes |
| `WARNING` | Failures + blocked requests |
| `INFO` | Every request (default) |
| `DEBUG` | Every request + cache hits + connection details |

Change level in `config.yaml` under `logging.level`, then Restart.

---

## Running Tests

```powershell
cd C:\Development\pyproxy
.venv\Scripts\Activate.ps1
pytest tests/ -v
```

Expected: **25 passed**

Tests cover: IP filter, domain filter, LRU cache, token-bucket bandwidth
throttler, and HTTP/1.x request parser.

---

## Troubleshooting

### Proxy icon doesn't appear in tray

- Make sure the script is actually running — open Task Manager and look
  for `pythonw.exe`
- Check the hidden icons area: click **`^`** in the taskbar
- Run from terminal to see errors:
  ```powershell
  python tray_app.py
  ```

### Proxy shows "Stopped" / won't start

Check `proxy.log` for errors. Common causes:

- **Port already in use** — change `port` in `config.yaml` to `8888` or any free port,
  then update Windows proxy settings to match
- **config.yaml has null lists** — replace commented list entries:
  ```yaml
  # WRONG (causes crash)
  ip_filter:
    mode: "none"
    list:
      # - "192.168.1.100"

  # CORRECT
  ip_filter:
    mode: "none"
    list: []
  ```

### Browser can't connect through proxy

1. Confirm proxy is running (green icon in tray)
2. Confirm Windows proxy settings: `127.0.0.1` port `8080`
3. Test directly:
   ```powershell
   python -c "import urllib.request; h=urllib.request.ProxyHandler({'http':'http://127.0.0.1:8080'}); o=urllib.request.build_opener(h); print(o.open('http://example.com').read(100))"
   ```
4. Check port is listening:
   ```powershell
   netstat -ano | findstr :8080
   ```
   You should see `LISTENING`. If not, the proxy crashed — check the log.

### McAfee blocks PyProxy.exe

The installer no longer uses `PyProxy.exe` — it uses `wscript.exe` (a
trusted Windows system binary) to launch `tray_app.py`. If McAfee still
complains, run directly from source:
```powershell
python tray_app.py
```
Python scripts are never flagged by antivirus.

### PowerShell `curl` doesn't work

PowerShell's `curl` is an alias for `Invoke-WebRequest`, not real curl.

```powershell
# Use this instead
Invoke-WebRequest -Uri http://example.com -Proxy http://127.0.0.1:8080

# Or use Python
python -c "import urllib.request; h=urllib.request.ProxyHandler({'http':'http://127.0.0.1:8080'}); o=urllib.request.build_opener(h); print(o.open('http://example.com').read(100))"
```

### build_installer.bat fails — Inno Setup not found

Make sure Inno Setup 6 is installed:
- Download: https://jrsoftware.org/isdl.php
- Default install path: `C:\Program Files (x86)\Inno Setup 6\`

### PermissionError when building — PyProxy.exe is running

```powershell
taskkill /f /im PyProxy.exe
taskkill /f /im pythonw.exe
.\build_installer.bat
```

### `ImportError: cannot import name 'ProxyServer' from 'proxy'`

`proxy\__init__.py` is missing. Create it:
```powershell
Set-Content proxy\__init__.py "from .config import load_config`nfrom .server import ProxyServer`n`n__all__ = ['load_config', 'ProxyServer']"
```