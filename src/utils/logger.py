"""
Centralised logger for the Nifty-100 Analytics pipeline.
Uses loguru with file + console sinks.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

# ── Remove default sink ──────────────────────────────────────────────────────
logger.remove()

# ── Config from env ──────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE: str = os.getenv("LOG_FILE", "logs/pipeline.log")

# ── Console sink (coloured) ───────────────────────────────────────────────────
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
    colorize=True,
)

# ── File sink (structured) ────────────────────────────────────────────────────
Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    enqueue=True,
)

__all__ = ["logger"]
