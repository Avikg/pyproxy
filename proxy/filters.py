"""
filters.py – IP allowlist/blocklist and domain allowlist/blocklist.
"""
from __future__ import annotations

import fnmatch
import ipaddress
from typing import List

from .config import FilterConfig
from .logger import get_logger

log = get_logger("proxy.filters")


class IPFilter:
    def __init__(self, cfg: FilterConfig):
        self.mode = cfg.mode.lower() if cfg.mode else "none"
        self._networks: List[ipaddress._BaseNetwork] = []

        for entry in (cfg.list or []):
            try:
                self._networks.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                log.warning("Invalid IP/CIDR in ip_filter list: %s", entry)

    def is_allowed(self, ip: str) -> bool:
        if self.mode == "none" or not self._networks:
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return True
        matched = any(addr in net for net in self._networks)
        if self.mode == "allowlist":
            return matched
        elif self.mode == "blocklist":
            return not matched
        return True


class DomainFilter:
    def __init__(self, cfg: FilterConfig):
        self.mode = cfg.mode.lower() if cfg.mode else "none"
        self._patterns: List[str] = [p.lower() for p in (cfg.list or [])]

    def is_allowed(self, host: str) -> bool:
        if self.mode == "none" or not self._patterns:
            return True
        host = host.lower()
        matched = any(fnmatch.fnmatch(host, pat) for pat in self._patterns)
        if self.mode == "allowlist":
            return matched
        elif self.mode == "blocklist":
            return not matched
        return True
