# Avik Proxy

A CCProxy-equivalent multi-protocol internet proxy server written in Python.
Runs silently as a **system tray application** with your custom **avik_proxy** icon.
Distributable to any Windows machine via a standard installer — no antivirus issues.

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Requirements](#requirements)
5. [Running from Source](#running-from-source)
6. [Building the Installer](#building-the-installer)
7. [Installing on Another Machine](#installing-on-another-machine)
8. [Windows Proxy Setup](#windows-proxy-setup)
9. [SOCKS5 Setup](#socks5-setup)
10. [TeamViewer Proxy Setup](#teamviewer-proxy-setup)
11. [System Tray Usage](#system-tray-usage)
12. [Configuration Reference](#configuration-reference)
13. [CLI Reference](#cli-reference)
14. [Blocking IPs and Domains](#blocking-ips-and-domains)
15. [Viewing Logs](#viewing-logs)
16. [Performance Notes](#performance-notes)
17. [Running Tests](#running-tests)
18. [Troubleshooting](#troubleshooting)

---

## Features

| Feature | Details |
|---|---|
| **HTTP proxy** | Full HTTP/1.x forwarding with URL rewriting and keep-alive |
| **HTTPS proxy** | CONNECT tunnel — TLS handled end-to-end by the client |
| **SOCKS5 proxy** | IPv4, IPv6, and domain name addressing |
| **FTP-over-HTTP** | Translates `ftp://` requests into real FTP downloads |
| **WebSocket support** | WS/WSS upgrades detected and tunnelled transparently |
| **Web cache** | In-memory LRU cache for HTTP GET responses |
| **IP filtering** | Allow or block clients by IP address or CIDR range |
| **Domain filtering** | Allow or block destinations by hostname or `*.wildcard` |
| **Bandwidth control** | Per-IP token-bucket throttler (KB/s) |
| **DNS cache** | Hostname resolved once per session — no repeated DNS lookups |
| **TCP_NODELAY** | Nagle disabled on all sockets for minimum latency |
| **Per-tunnel threads** | Every CONNECT gets its own thread — no worker starvation |
| **System tray** | Custom avik_proxy icon, live stats, no console window |
| **Rotating log** | Console + rotating file log |
| **Inno Setup installer** | `AvikProxySetup.exe` — installs like normal software, no antivirus false positives |

---

## Architecture

```
Client (browser / app)
        │
        │  HTTP  HTTPS(CONNECT)  SOCKS5  FTP-over-HTTP  WebSocket
        ▼
┌───────────────────────────────┐
│  TCP Server  (port 8080)      │  Thread pool — 200 workers
│  TCP_NODELAY + SO_REUSEADDR   │  DNS LRU cache (1024 entries)
└──────────────┬────────────────┘  IPv4-preferred resolution
               │
               ▼
┌───────────────────────────────┐
│  IP Filter                    │  Allow/block by IP or CIDR
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│  Protocol Detect              │  SOCKS5 (0x05) vs HTTP/FTP
└──────┬────────────────────────┘
       │
  ┌────┴─────────────────────────────────────────────┐
  │                                                  │
  ▼                                                  ▼
SOCKS5 handler                              HTTP keep-alive loop
  │                                           (max 50 req, 30s idle)
  │                                                  │
  │                              ┌───────────────────┼──────────────────┐
  │                              │                   │                  │
  │                         Domain filter       CONNECT             Plain HTTP
  │                              │                   │                  │
  │                              │            ┌──────▼──────┐    ┌──────▼──────┐
  │                              │            │ Relay thread│    │ Cache lookup│
  │                              │            │ (dedicated) │    │ + forward   │
  │                              │            │ 5min idle   │    └─────────────┘
  │                              │            └─────────────┘
  │                              │
  │                         WebSocket?
  │                              │
  │                         ┌────▼────────┐
  │                         │ Relay thread│
  │                         │ (dedicated) │
  │                         └─────────────┘
  │
  ▼ (own relay thread)
Remote server (internet)
```

### Key design: per-tunnel threads

Every `CONNECT` (HTTPS/WSS) and SOCKS5 connection spawns its own **dedicated relay thread**.
The worker thread is freed immediately — it doesn't wait for the tunnel to close.
This matches CCProxy's behaviour and prevents one long-lived connection
(e.g. Outlook, Teams, Dropbox) from blocking all other requests.

| Protocol | Behaviour |
|---|---|
| **HTTP** | Keep-alive loop — up to 50 requests per connection, 30s idle timeout |
| **HTTPS** | CONNECT → relay thread spawned → worker freed immediately |
| **WebSocket** | Upgrade forwarded → relay thread spawned → worker freed |
| **SOCKS5** | Full RFC 1928; relay thread spawned after handshake |
| **FTP-over-HTTP** | `GET ftp://host/path` → anonymous FTP download → HTTP 200 |

---

## Project Structure

```
pyproxy/
│
├── tray_app.py              System tray entry point — run this
├── main.py                  CLI / headless entry point
│
├── avik_proxy.ico           Custom tray icon (multi-resolution .ico)
├── avik_proxy.png           Custom tray icon (.png, used by tray at runtime)
│
├── build_installer.bat      One-click installer build script
├── pyproxy_installer.iss    Inno Setup installer configuration
├── requirements.txt         All dependencies (dev + runtime)
├── requirements_runtime.txt Runtime-only dependencies (bundled in installer)
│
├── config.yaml              Configuration file — edit to change settings
│
└── proxy/                   Core proxy package
    ├── __init__.py          Exports ProxyServer, load_config
    ├── server.py            Thread-pool TCP server + DNS LRU cache
    ├── handler.py           Per-connection dispatcher (per-tunnel threads)
    ├── http_parser.py       HTTP/1.x request parser
    ├── ftp_handler.py       FTP-over-HTTP translator
    ├── filters.py           IP and domain allow/blocklist
    ├── cache.py             Thread-safe LRU response cache
    ├── bandwidth.py         Token-bucket bandwidth throttler
    ├── stats.py             Live metrics collector (singleton)
    ├── config.py            Config dataclasses and YAML loader
    └── logger.py            Console + rotating file log setup
```

---

## Requirements

### Build machine (your machine)
- Python **3.10 or newer** — https://python.org/downloads
- Inno Setup 6 — https://jrsoftware.org/isdl.php
- Windows 10 / 11

### Target machine (where proxy runs)
- Python **3.10 or newer** — https://python.org/downloads
  - During install: tick **"Add Python to PATH"**
- Windows 10 / 11
- No VS Code, no terminal, no other tools needed

---

## Running from Source

Use this during development — no rebuild needed after code changes.

### Step 1 — Clone / download

```
C:\Development\pyproxy\
├── tray_app.py
├── main.py
├── config.yaml
├── avik_proxy.ico
├── avik_proxy.png
├── requirements.txt
└── proxy\
    └── (all .py files)
```

### Step 2 — Create virtual environment

```powershell
cd C:\Development\pyproxy
python -m venv .venv
```

### Step 3 — Activate

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
# Tray mode — silently runs in system tray with custom icon
python tray_app.py

# CLI / headless — logs printed to terminal
python main.py
```

The **avik_proxy icon** appears in the system tray (bottom-right taskbar).
Right-click for controls.

---

## Building the Installer

Produces `AvikProxySetup.exe` — a standard Windows installer that won't trigger antivirus.

---

### Step 1 — Install Inno Setup (one-time, free)

1. Go to **https://jrsoftware.org/isdl.php**
2. Click **"Download Inno Setup 6"**
3. Run the downloaded `isetup-6.x.x.exe`
4. Click Next → Next → Install
5. Default install path: `C:\Program Files (x86)\Inno Setup 6\`

---

### Step 2 — Set up virtual environment (if not done)

```powershell
cd C:\Development\pyproxy
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

### Step 3 — Run the build script

```powershell
cd C:\Development\pyproxy
.\build_installer.bat
```

> **Note:** Always use `.\` prefix in PowerShell to run local scripts.

**What the build script does automatically:**

```
[1/3] Activates .venv
      Runs: pip install PyYAML pystray Pillow --quiet

[2/3] Runs Inno Setup compiler
      Command: ISCC.exe pyproxy_installer.iss

[3/3] Done — installer written to installer_output\AvikProxySetup.exe
```

---

### Step 4 — Find your installer

```
C:\Development\pyproxy\
└── installer_output\
    └── AvikProxySetup.exe    ← this is your distributable file
```

Send this single file to any Windows machine that has Python installed.

---

### Rebuild after code changes

Any time you edit a `.py` file, rebuild to get a fresh installer:

```powershell
# Kill any running instance first
taskkill /f /im pythonw.exe 2>$null

# Rebuild
cd C:\Development\pyproxy
.\build_installer.bat
```

---

### Manual build (step by step)

If `build_installer.bat` fails, you can run each step manually:

```powershell
# 1. Activate venv
cd C:\Development\pyproxy
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install PyYAML pystray Pillow pyinstaller

# 3. Run Inno Setup compiler directly
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" pyproxy_installer.iss

# 4. Check output
dir installer_output\
```

---

### Build troubleshooting

| Error | Fix |
|---|---|
| `'build.bat' is not recognized` | Use `.\build_installer.bat` not `build_installer.bat` |
| `Inno Setup not found` | Install from https://jrsoftware.org/isdl.php |
| `PermissionError: Access is denied` | Run `taskkill /f /im pythonw.exe` first, then rebuild |
| `McAfee blocked AvikProxySetup.exe` | Open McAfee → Antivirus → Review threats → Restore |
| `Python not found` | Install Python from https://python.org, tick "Add to PATH" |
| `pip install failed` | Run `python -m pip install --upgrade pip` then retry |

---

### Output

```
installer_output\
└── AvikProxySetup.exe    ← send this to any target machine
```

---

## Installing on Another Machine

### Prerequisites on target machine
- Windows 10 / 11
- Python 3.10+ from https://python.org/downloads
  - Tick **"Add Python to PATH"** during installation

### Steps

1. Copy `AvikProxySetup.exe` to target machine
2. Double-click it — a setup wizard opens:

```
Welcome                 → Next
Select Destination      → Default: C:\Users\<you>\AppData\Local\Avik Proxy
                          → Next
Additional Tasks
  ☐ Create desktop shortcut          (optional)
  ☐ Start Avik Proxy when Windows starts  (optional — recommended for LAN proxy)
                        → Next
Ready to Install        → Install

Installing…
  Copies all .py files
  Installs: pip install pystray Pillow PyYAML  (silently)
  Creates start.vbs launcher

Finish
  ☑ Launch Avik Proxy now  → Finish
```

3. Avik proxy icon appears in system tray — proxy is running.

### What gets installed

```
C:\Users\<you>\AppData\Local\Avik Proxy\
├── tray_app.py              Main script
├── main.py                  CLI script
├── start.vbs                Silent launcher (used by shortcuts)
├── avik_proxy.ico           Tray icon
├── avik_proxy.png           Tray icon (PNG)
├── config.yaml              Configuration (safe to edit)
└── proxy\                   Core proxy package
    └── (all .py files)
```

Start Menu:
- **Avik Proxy** — starts the proxy
- **Uninstall Avik Proxy** — removes everything

### Uninstall

- **Settings → Apps → Avik Proxy → Uninstall**
- or: **Start Menu → Avik Proxy → Uninstall Avik Proxy**

### Why no antivirus issues

The installer uses `wscript.exe` (a trusted Windows system binary) to launch
`tray_app.py` — no PyInstaller-bundled exe, no self-extracting packer.
Antivirus tools never flag `.py` scripts or `wscript.exe`.

---

## Windows Proxy Setup

Configure Windows to route all traffic through Avik Proxy:

1. **Settings → Network & Internet → Proxy**
2. Under *Manual proxy setup*, click **Set up**
3. Toggle **"Use a proxy server"** → **On**
4. Address: `127.0.0.1`
5. Port: `8080`
6. Click **Save**

All HTTP and HTTPS traffic from browsers (Chrome, Edge, Firefox) and most
Windows apps will now route through the proxy.

To verify: right-click tray icon — status should show `● Running  127.0.0.1:8080`
and request count increases as you browse.

---

## SOCKS5 Setup

SOCKS5 runs on the **same port** (8080 by default).

### Firefox

1. **Options → General → Network Settings → Manual proxy configuration**
2. SOCKS Host: `127.0.0.1`  Port: `8080`
3. Select **SOCKS v5**
4. Check **"Proxy DNS when using SOCKS v5"**
5. Click **OK**

### Chrome / Edge

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

## TeamViewer Proxy Setup

TeamViewer ignores the Windows system proxy — it must be configured inside the app.

1. Open TeamViewer
2. **Extras → Options → General → Network settings**
3. Under **Proxy settings**, select **"Use manual proxy"**
4. Host: `127.0.0.1`   Port: `8080`
5. Click **OK**

Other apps that need manual proxy configuration:

| App | Where to configure |
|---|---|
| TeamViewer | Extras → Options → Network |
| Zoom | Settings → General → Network Proxy |
| Slack | File → Preferences → Advanced → Network |
| VS Code | Settings → search "proxy" |
| Firefox | Options → Network Settings |
| Chrome/Edge | Uses Windows system proxy automatically |

---

## System Tray Usage

The **avik_proxy icon** lives in the system tray (bottom-right of taskbar).
If not visible, click **`^`** to show hidden icons.

### Icon states

| Icon | Meaning |
|---|---|
| Full colour (purple/green) | Proxy is running |
| Greyscale | Proxy is stopped |

### Right-click menu

```
Avik Proxy
● Running  127.0.0.1:8080          ← status (not clickable)
Reqs: 142  Blocked: 3  Uptime: 8m  ← live stats (updates every 5s)
───────────────────────────────────
Start                               ← greyed out when running
Stop
Restart
───────────────────────────────────
View Log                            ← opens proxy.log in Notepad
Open Config                         ← opens config.yaml in Notepad
───────────────────────────────────
Quit                                ← stops proxy and exits tray
```

### Applying config changes

1. Right-click → **Open Config**
2. Edit and save `config.yaml`
3. Right-click → **Restart**

---

## Configuration Reference

`config.yaml` is next to the installed scripts.
All changes require a **Restart** to take effect.

```yaml
# ── Server ────────────────────────────────────────────────────────────────────
server:
  host: "0.0.0.0"       # Bind address. Use 127.0.0.1 for localhost only.
  port: 8080            # Port for HTTP, HTTPS, SOCKS5, FTP, WebSocket.
  workers: 200          # Thread pool size for accepting new connections.
                        # Tunnels use their own threads — this can be lower.

# ── Logging ───────────────────────────────────────────────────────────────────
logging:
  level: "INFO"         # DEBUG | INFO | WARNING | ERROR
  log_file: proxy.log   # Relative = next to config.yaml
  max_bytes: 10485760   # Max size per log file (10 MB)
  backup_count: 5       # Number of old log files to keep

# ── Web Cache ─────────────────────────────────────────────────────────────────
cache:
  enabled: true         # false = disable caching entirely
  max_size: 512         # Max number of cached responses (in memory)
  ttl: 300              # Seconds before a cached response expires

# ── Bandwidth Control ─────────────────────────────────────────────────────────
bandwidth:
  enabled: true         # false = disable throttling entirely
  default_kbps: 0       # Default cap for all clients. 0 = unlimited.
  per_ip:               # Per-client overrides
    "192.168.1.50": 512   # Limit this IP to 512 KB/s
    "192.168.1.51": 1024  # Limit this IP to 1024 KB/s

# ── IP Filter ─────────────────────────────────────────────────────────────────
ip_filter:
  mode: "none"          # none | allowlist | blocklist
  list:
    - "192.168.1.100"   # exact IP
    - "10.0.0.0/8"      # CIDR range

# ── Domain Filter ─────────────────────────────────────────────────────────────
domain_filter:
  mode: "blocklist"     # none | allowlist | blocklist
  list:
    # Windows IPv6 connectivity checks — always fail, cause slowness
    - "ipv6.msftncsi.com"
    - "ipv6.msftconnecttest.com"
    - "teredo.ipv6.microsoft.com"
    # Add your own blocked domains below:
    # - "ads.example.com"
    # - "*.tracker.net"
```

### Critical rules

- **`list: []`** — always use an explicit empty list when empty. Commented-out entries leave the field as `null` and cause a startup crash.
- **`per_ip: {}`** — always use explicit empty map `{}` when no per-IP rules are set.
- CIDR notation is supported: `10.0.0.0/8`, `192.168.0.0/24`
- Wildcards like `*.ads.com` match subdomains but NOT the bare domain `ads.com`

---

## CLI Reference

`main.py` provides headless mode — all output goes to the terminal.
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
# Start with defaults from config.yaml
python main.py

# Debug mode on a custom port
python main.py --port 9090 --log-level DEBUG

# Localhost only (won't accept LAN clients)
python main.py --host 127.0.0.1

# Custom config file
python main.py --config C:\Users\me\myproxy.yaml
```

---

## Blocking IPs and Domains

Edit `config.yaml`, save, then right-click tray → **Restart**.

### Block specific IPs

```yaml
ip_filter:
  mode: "blocklist"
  list:
    - "192.168.1.55"
    - "192.168.1.80"
```

### Block an entire IP range (CIDR)

```yaml
ip_filter:
  mode: "blocklist"
  list:
    - "10.0.0.0/8"
    - "172.16.0.0/12"
```

### Allow only specific IPs (LAN whitelist)

```yaml
ip_filter:
  mode: "allowlist"
  list:
    - "192.168.0.0/24"   # your whole LAN subnet
```

### Block websites / domains

```yaml
domain_filter:
  mode: "blocklist"
  list:
    - "ads.example.com"
    - "*.doubleclick.net"
    - "*.googlesyndication.com"
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
    - "*.github.com"
```

Blocked requests get an immediate HTTP 403 and are logged as `BLOCKED`.

---

## Viewing Logs

### From tray

Right-click tray icon → **View Log** — opens `proxy.log` in Notepad.

### Log file location

| Mode | Location |
|---|---|
| Running from source | `C:\Development\pyproxy\proxy.log` |
| Installed | `C:\Users\<you>\AppData\Local\Avik Proxy\proxy.log` |

### Log format

```
2026-03-17 20:02:47 [INFO]    worker_5  – CONNECT tunnel d.dropbox.com:443 [192.168.0.199]
2026-03-17 20:02:47 [INFO]    worker_28 – HTTP GET msedge.b.tlu.dl.delivery.mp.microsoft.com:80/... [192.168.0.199]
2026-03-17 20:02:49 [ERROR]   worker_41 – Cannot reach ipv6.msftncsi.com:80 – getaddrinfo failed
2026-03-17 20:02:49 [WARNING] worker_2  – Blocked domain: ads.tracker.net [192.168.0.199]
```

### Log levels

| Level | Shows |
|---|---|
| `ERROR` | Failures and crashes only |
| `WARNING` | Failures + blocked requests |
| `INFO` | Every request (default — recommended) |
| `DEBUG` | Everything including cache hits, DNS, headers |

---

## Performance Notes

### Why it's fast

- **DNS LRU cache** — every hostname resolved once and cached for the session. No repeated DNS lookups per request.
- **IPv4-preferred DNS** — `AF_INET` used first, avoiding IPv6 timeout delays on networks without IPv6 routing.
- **Per-tunnel threads** — every CONNECT spawns its own relay thread. One long-lived connection (Outlook staying open for hours) never delays a browser request.
- **TCP_NODELAY** — Nagle's algorithm disabled on all sockets. Small packets sent immediately.
- **IPv6 connectivity hosts short-circuited** — `ipv6.msftncsi.com` and similar Windows diagnostic hosts that always fail DNS are rejected instantly in code (before DNS lookup), saving 10s per attempt.
- **HTTP keep-alive** — up to 50 requests reuse the same TCP connection.

### Tuning for large LANs

If you have many users (20+), increase workers in `config.yaml`:

```yaml
server:
  workers: 500
```

Workers only consume memory when active. Setting it high is safe — idle workers cost almost nothing.

### Windows Widgets / sidebar loading slowly

This is caused by Windows making WebSocket connections that our proxy now handles correctly. If it still loads slowly:
1. Make sure `handler.py` is the latest version (with per-tunnel threads)
2. Add the domain to bypass if needed — set Windows proxy exception for `*.microsoft.com`

---

## Running Tests

```powershell
cd C:\Development\pyproxy
.venv\Scripts\Activate.ps1
pytest tests/ -v
```

Expected: **25 passed**

Covers: IP filter, domain filter, LRU cache, token-bucket bandwidth throttler, HTTP/1.x parser.

---

## Troubleshooting

### Proxy icon doesn't appear in tray

```powershell
# Run from terminal to see errors
python tray_app.py
```

Check hidden icons — click **`^`** in the taskbar corner.

---

### Proxy stuck on "Stopped" / won't start

Check `proxy.log` for errors. Most common causes:

**Port already in use:**
```powershell
netstat -ano | findstr :8080
```
If occupied, change `port` in `config.yaml` and update Windows proxy settings to match.

**config.yaml has null lists (startup crash):**
```yaml
# WRONG — commented entries leave field as null
ip_filter:
  mode: "none"
  list:
    # - "192.168.1.100"

# CORRECT
ip_filter:
  mode: "none"
  list: []

# WRONG
bandwidth:
  per_ip:
    # "192.168.1.50": 512

# CORRECT
bandwidth:
  per_ip: {}
```

---

### Browser can't connect through proxy

1. Confirm proxy is running (coloured icon in tray)
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

---

### Pages loading slowly

Check `proxy.log` for repeated `getaddrinfo failed` errors on IPv6 hosts.
If you see `ipv6.msftncsi.com` errors, make sure your `config.yaml` has
the blocklist entries:

```yaml
domain_filter:
  mode: "blocklist"
  list:
    - "ipv6.msftncsi.com"
    - "ipv6.msftconnecttest.com"
    - "teredo.ipv6.microsoft.com"
```

Also ensure you have the latest `handler.py` with per-tunnel threads.

---

### Windows Widgets / sidebar not loading

This requires WebSocket support. Make sure `proxy\handler.py` is the latest
version. The current handler detects WebSocket upgrades and spawns dedicated
relay threads for them.

If still failing, add a proxy exception in Windows:
**Settings → Network & Internet → Proxy → Set up → Exceptions:**
```
*.microsoft.com;*.msn.com;*.live.com
```

---

### McAfee blocking the installer or scripts

The installer uses `wscript.exe` (a trusted Windows system binary) to launch
`tray_app.py`. Python `.py` scripts are never flagged by antivirus.

If McAfee quarantines something:
1. Open McAfee → Antivirus → Review threats
2. Click **Restore** on the quarantined item
3. Click **Trust this file**

Or run directly from source — never gets flagged:
```powershell
python tray_app.py
```

---

### `taskkill /f /im PyProxy.exe` needed before rebuild

```powershell
taskkill /f /im PyProxy.exe 2>$null
taskkill /f /im pythonw.exe 2>$null
.\build_installer.bat
```

---

### PowerShell `curl` doesn't work

PowerShell's `curl` is an alias for `Invoke-WebRequest`. Use:

```powershell
# PowerShell native
Invoke-WebRequest -Uri http://example.com -Proxy http://127.0.0.1:8080

# Real curl (if installed)
curl.exe -x http://127.0.0.1:8080 http://example.com

# Python test
python -c "import urllib.request; h=urllib.request.ProxyHandler({'http':'http://127.0.0.1:8080'}); o=urllib.request.build_opener(h); print(o.open('http://example.com').read(100))"
```

---

### `ImportError: cannot import name 'ProxyServer' from 'proxy'`

`proxy\__init__.py` is missing. Recreate it:

```powershell
Set-Content proxy\__init__.py "from .config import load_config`nfrom .server import ProxyServer`n`n__all__ = ['load_config', 'ProxyServer']"
```

---

### build_installer.bat fails — Inno Setup not found

Install from: https://jrsoftware.org/isdl.php
Default path: `C:\Program Files (x86)\Inno Setup 6\`