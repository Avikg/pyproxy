# PyProxy

A CCProxy-style multi-protocol internet proxy server written in Python.

## Features

| Feature | Details |
|---|---|
| **Protocols** | HTTP, HTTPS (CONNECT tunnel), SOCKS5, FTP-over-HTTP |
| **Logging** | Console + rotating log file |
| **IP filter** | None / allowlist / blocklist (supports CIDR ranges) |
| **Domain filter** | None / allowlist / blocklist (supports `*.wildcard` patterns) |
| **Web cache** | In-memory LRU cache for HTTP GET responses, configurable TTL |
| **Bandwidth control** | Token-bucket throttler per client IP |
| **Concurrency** | Thread-pool (configurable worker count) |

---

## Quick Start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the proxy
python main.py
```

Default port: **8080**

### Windows Proxy Settings

1. Open **Settings → Network & Internet → Proxy**
2. Enable **"Use a proxy server"**
3. Address: `127.0.0.1`  Port: `8080`
4. Click **Save**

---

## Configuration (`config.yaml`)

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  workers: 50

logging:
  level: "INFO"           # DEBUG | INFO | WARNING | ERROR
  log_file: "proxy.log"
  max_bytes: 10485760     # 10 MB
  backup_count: 5

cache:
  enabled: true
  max_size: 256           # cached entries
  ttl: 300                # seconds

bandwidth:
  enabled: true
  default_kbps: 0         # 0 = unlimited
  per_ip:
    "192.168.1.50": 512   # throttle specific IP to 512 KB/s

ip_filter:
  mode: "none"            # none | allowlist | blocklist
  list:
    - "192.168.1.0/24"

domain_filter:
  mode: "none"            # none | allowlist | blocklist
  list:
    - "*.ads.com"
    - "tracker.net"
```

---

## CLI Overrides

```bash
python main.py --host 0.0.0.0 --port 9090 --workers 100 --log-level DEBUG
python main.py --config /etc/pyproxy/config.yaml
```

---

## Project Structure

```
pyproxy/
├── main.py                 # Entry point
├── config.yaml             # Configuration file
├── requirements.txt
└── proxy/
    ├── __init__.py
    ├── config.py           # Config loader & dataclasses
    ├── logger.py           # Rotating log + console setup
    ├── filters.py          # IP and domain filtering
    ├── cache.py            # LRU response cache
    ├── bandwidth.py        # Token-bucket throttler
    ├── http_parser.py      # HTTP/1.x request parser
    ├── ftp_handler.py      # FTP-over-HTTP handler
    ├── handler.py          # Per-connection dispatcher
    └── server.py           # Thread-pool TCP server
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## SOCKS5 Setup (Firefox example)

1. **Options → General → Network Settings → Manual proxy**
2. SOCKS Host: `127.0.0.1`  Port: `8080`
3. Select **SOCKS v5**
