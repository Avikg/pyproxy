#!/usr/bin/env python3
"""
main.py – Entry point for PyProxy.

Usage:
    python main.py                        # uses config.yaml in CWD
    python main.py --config /path/to.yaml
    python main.py --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import argparse
import sys

from proxy import ProxyServer, load_config


def parse_args():
    p = argparse.ArgumentParser(description="PyProxy – multi-protocol proxy server")
    p.add_argument("--config", default=None, help="Path to config.yaml")
    p.add_argument("--host", default=None, help="Bind host (overrides config)")
    p.add_argument("--port", type=int, default=None, help="Bind port (overrides config)")
    p.add_argument("--workers", type=int, default=None, help="Thread-pool size (overrides config)")
    p.add_argument("--log-level", default=None, help="Logging level: DEBUG|INFO|WARNING|ERROR")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)

    # CLI overrides
    if args.host:
        cfg.server.host = args.host
    if args.port:
        cfg.server.port = args.port
    if args.workers:
        cfg.server.workers = args.workers
    if args.log_level:
        cfg.logging.level = args.log_level.upper()

    server = ProxyServer(cfg)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
