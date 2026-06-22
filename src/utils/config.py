"""
Configuration loader — reads .env and exposes typed settings.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (safe to call multiple times)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)


class Config:
    """Central configuration object derived from environment variables."""

    # Paths
    PROJECT_ROOT: Path = Path(os.getenv("PROJECT_ROOT", ".")).resolve()
    DB_PATH: Path = PROJECT_ROOT / os.getenv("DB_PATH", "nifty100.db")
    RAW_DATA_DIR: Path = PROJECT_ROOT / os.getenv("RAW_DATA_DIR", "data/raw")
    OUTPUT_DIR: Path = PROJECT_ROOT / os.getenv("OUTPUT_DIR", "output")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/pipeline.log")

    # SQLite
    SQLITE_FOREIGN_KEYS: str = os.getenv("SQLITE_FOREIGN_KEYS", "ON")
    SQLITE_JOURNAL_MODE: str = os.getenv("SQLITE_JOURNAL_MODE", "WAL")

    # Source file manifest — 7 core + 5 supplementary
    CORE_FILES: list[str] = [
        "profit_and_loss.xlsx",
        "balance_sheet.xlsx",
        "cash_flow.xlsx",
        "companies.xlsx",
        "sectors.xlsx",
        "stock_prices.xlsx",
        "financial_ratios.xlsx",
    ]

    SUPPLEMENTARY_FILES: list[str] = [
        "analysis.xlsx",
        "documents.xlsx",
        "prosandcons.xlsx",
        "peer_groups.xlsx",      # maps to prosandcons / analysis in extended schema
        "market_data.xlsx",
    ]

    # Expected row counts (Sprint 1 exit criteria)
    EXPECTED_COUNTS: dict[str, int] = {
        "companies":      92,
        "profitandloss":  1276,
        "balancesheet":   1312,
        "cashflow":       1187,
        "stock_prices":   5520,
    }

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create output/log directories if they don't exist."""
        for d in [cls.OUTPUT_DIR, cls.RAW_DATA_DIR, Path("logs")]:
            d.mkdir(parents=True, exist_ok=True)


cfg = Config()
