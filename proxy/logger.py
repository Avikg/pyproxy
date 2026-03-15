"""
logger.py – Configure root logger: console + rotating file handler.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import LoggingConfig

_configured = False


def setup_logging(cfg: LoggingConfig) -> logging.Logger:
    global _configured
    if _configured:
        return logging.getLogger("proxy")

    level = getattr(logging, cfg.level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("proxy")
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Rotating file handler
    fh = RotatingFileHandler(
        cfg.log_file,
        maxBytes=cfg.max_bytes,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    _configured = True
    return root


def get_logger(name: str = "proxy") -> logging.Logger:
    return logging.getLogger(name)
