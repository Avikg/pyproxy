"""
config.py – Load and validate config.yaml, expose a singleton Config object.
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Sub-sections
# ---------------------------------------------------------------------------

@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 50


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_file: str = "proxy.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class CacheConfig:
    enabled: bool = True
    max_size: int = 256
    ttl: int = 300


@dataclass
class BandwidthConfig:
    enabled: bool = True
    default_kbps: int = 0
    per_ip: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.per_ip is None:
            self.per_ip = {}


@dataclass
class FilterConfig:
    mode: str = "none"
    list: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.list is None:
            self.list = []


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    bandwidth: BandwidthConfig = field(default_factory=BandwidthConfig)
    ip_filter: FilterConfig = field(default_factory=FilterConfig)
    domain_filter: FilterConfig = field(default_factory=FilterConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _merge(dataclass_obj, d: dict):
    """Recursively set fields on a dataclass from a dict."""
    if not d:
        return
    for key, value in d.items():
        if hasattr(dataclass_obj, key):
            attr = getattr(dataclass_obj, key)
            if hasattr(attr, '__dataclass_fields__'):
                _merge(attr, value)
            else:
                setattr(dataclass_obj, key, value)


def load_config(path: Optional[str] = None) -> Config:
    cfg = Config()

    search = [path] if path else [
        "config.yaml",
        os.path.join(os.path.dirname(__file__), "..", "config.yaml"),
    ]

    for p in search:
        if p and os.path.isfile(p):
            with open(p, "r") as f:
                raw = yaml.safe_load(f) or {}
            _merge(cfg, raw)
            break

    return cfg


def validate_ip_or_cidr(entry: str) -> bool:
    try:
        ipaddress.ip_network(entry, strict=False)
        return True
    except ValueError:
        return False
