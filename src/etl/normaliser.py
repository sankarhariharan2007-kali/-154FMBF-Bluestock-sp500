"""
normaliser.py — data normalisation utilities for the Nifty-100 ETL pipeline.

Key public functions
--------------------
normalize_year(raw)        → int  (fiscal year ending, e.g. 2023)
normalize_ticker(raw)      → str  (clean NSE ticker)
normalize_column_name(raw) → str  (snake_case column header)
normalize_numeric(raw)     → float | None
clean_string(raw)          → str | None
"""
from __future__ import annotations

import re
from typing import Any

from src.utils.logger import logger

# ── Fiscal year normalisation ─────────────────────────────────────────────────

_FY_PATTERNS: list[tuple[re.Pattern, int]] = [
    # "FY2023", "FY 2023", "fy2023"
    (re.compile(r"(?i)fy\s*(\d{4})$"), 0),
    # "2022-23", "2022-2023", "2022/23", "2022/2023"
    (re.compile(r"(\d{4})[-/](\d{2,4})$"), 1),
    # "Mar-2023", "March 2023", "Mar'23"
    (re.compile(r"(?i)(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)['\-\s]*(\d{2,4})$"), 2),
    # Plain 4-digit year: "2023"
    (re.compile(r"^(\d{4})$"), 3),
    # 2-digit year "23" → ambiguous, assume 2000+
    (re.compile(r"^(\d{2})$"), 4),
]


def normalize_year(raw: Any) -> int:
    """
    Convert various fiscal-year representations to a single integer.

    The integer represents the **ending** calendar year of the fiscal year.
    Examples
    --------
    >>> normalize_year("FY2023")
    2023
    >>> normalize_year("2022-23")
    2023
    >>> normalize_year("Mar-2023")
    2023
    >>> normalize_year(2022)
    2022
    >>> normalize_year("22")
    2022
    """
    if raw is None:
        raise ValueError("Cannot normalise None year.")

    # Numeric types
    if isinstance(raw, (int, float)):
        yr = int(raw)
        if 1990 <= yr <= 2100:
            return yr
        if 90 <= yr <= 99:
            return 1900 + yr
        if 0 <= yr <= 30:
            return 2000 + yr
        raise ValueError(f"Unrecognisable numeric year: {raw!r}")

    text = str(raw).strip().replace(",", "")

    # Pattern 0: FY2023
    m = re.match(r"(?i)fy\s*(\d{4})$", text)
    if m:
        return int(m.group(1))

    # Pattern 1: 2022-23 / 2022-2023 / 2022/23
    m = re.match(r"(\d{4})[-/](\d{2,4})$", text)
    if m:
        suffix = m.group(2)
        if len(suffix) == 2:
            return int(m.group(1)[:2] + suffix)
        return int(suffix)

    # Pattern 2: Mar-2023 / March 2023 / March2023
    m = re.match(
        r"(?i)(?:january|february|march|april|may|june|july|august|september|october|november|december"
        r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)['\-\s]*(\d{2,4})$",
        text,
    )
    if m:
        yr_str = m.group(1)
        return 2000 + int(yr_str) if len(yr_str) == 2 else int(yr_str)

    # Pattern 3: plain 4-digit
    m = re.match(r"^(\d{4})$", text)
    if m:
        return int(m.group(1))

    # Pattern 4: 2-digit
    m = re.match(r"^(\d{2})$", text)
    if m:
        yr = int(m.group(1))
        return 2000 + yr if yr <= 30 else 1900 + yr

    raise ValueError(f"Cannot normalise year from: {raw!r}")


# ── Ticker normalisation ──────────────────────────────────────────────────────

_TICKER_STRIP: re.Pattern = re.compile(r"[^A-Z0-9&\-\.]")
_KNOWN_SUFFIXES: tuple[str, ...] = (".NS", ".BO", ".BSE", ".NSE")


def normalize_ticker(raw: Any) -> str:
    """
    Return a clean, upper-cased NSE ticker symbol.

    - Strips whitespace and exchange suffixes (.NS, .BO, etc.)
    - Upper-cases
    - Replaces common full-names with their ticker equivalents when obvious

    Examples
    --------
    >>> normalize_ticker("reliance.NS")
    'RELIANCE'
    >>> normalize_ticker(" TCS ")
    'TCS'
    >>> normalize_ticker("HDFC BANK")
    'HDFCBANK'
    """
    if raw is None or str(raw).strip() == "":
        raise ValueError("Ticker cannot be empty.")

    ticker = str(raw).strip().upper()

    # Remove known exchange suffixes
    for suffix in _KNOWN_SUFFIXES:
        if ticker.endswith(suffix):
            ticker = ticker[: -len(suffix)]

    # Remove spaces within tickers (e.g. "HDFC BANK" → "HDFCBANK")
    ticker = ticker.replace(" ", "")

    # Strip non-standard chars (keep alphanumeric, &, -, .)
    ticker = _TICKER_STRIP.sub("", ticker)

    if not ticker:
        raise ValueError(f"Ticker normalised to empty string from: {raw!r}")

    return ticker


# ── Column-name normalisation ─────────────────────────────────────────────────

def normalize_column_name(raw: str) -> str:
    """
    Convert an Excel column header to a clean snake_case identifier.

    Examples
    --------
    >>> normalize_column_name("Net Profit (₹ Cr)")
    'net_profit_cr'
    >>> normalize_column_name("OPM %")
    'opm_pct'
    >>> normalize_column_name("P/E Ratio")
    'pe_ratio'
    """
    col = str(raw).strip()

    # Replace percent-like tokens
    col = re.sub(r"%", " pct", col)
    # Remove currency symbols and parenthetical units
    col = re.sub(r"[₹$€£()\[\]{}]", " ", col)
    # Remove common noise chars
    col = re.sub(r"[/\\:,\-]", " ", col)
    # Lowercase
    col = col.lower()
    # Collapse whitespace → underscore
    col = re.sub(r"\s+", "_", col.strip())
    # Remove trailing/leading underscores
    col = col.strip("_")
    # Collapse repeated underscores
    col = re.sub(r"_+", "_", col)
    return col


# ── Numeric normalisation ─────────────────────────────────────────────────────

_CRORE_RE  = re.compile(r"(?i)cr\.?$")
_MILLION_RE = re.compile(r"(?i)(mn|million)\.?$")
_BILLION_RE = re.compile(r"(?i)(bn|billion)\.?$")


def normalize_numeric(raw: Any, unit_multiplier: float = 1.0) -> float | None:
    """
    Parse a numeric cell that may contain commas, currency prefixes,
    or unit suffixes (Cr, Mn, Bn).

    Returns None for blanks / truly non-numeric cells.

    Examples
    --------
    >>> normalize_numeric("1,23,456.78")
    123456.78
    >>> normalize_numeric("₹ 1,234 Cr")   # stored as-is; multiplier applied externally
    1234.0
    >>> normalize_numeric(None)
    None
    """
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        return float(raw) * unit_multiplier

    text = str(raw).strip()
    if text in ("", "-", "—", "N/A", "NA", "n/a", "nan", "NaN"):
        return None

    # Strip currency symbols
    text = re.sub(r"[₹$€£]", "", text).strip()

    # Detect and strip unit suffix — apply multiplier implicitly later if caller passes one
    multiplier = unit_multiplier
    if _CRORE_RE.search(text):
        text = _CRORE_RE.sub("", text).strip()
    elif _MILLION_RE.search(text):
        text = _MILLION_RE.sub("", text).strip()
        multiplier *= 0.1  # 1 Mn = 0.1 Cr (rough; caller should standardise)
    elif _BILLION_RE.search(text):
        text = _BILLION_RE.sub("", text).strip()
        multiplier *= 100.0  # 1 Bn = 100 Cr

    # Remove commas (Indian / international thousands separators)
    text = text.replace(",", "")

    try:
        return float(text) * multiplier
    except ValueError:
        logger.debug(f"normalize_numeric: could not parse {raw!r}")
        return None


# ── String cleaning ───────────────────────────────────────────────────────────

def clean_string(raw: Any, max_len: int | None = None) -> str | None:
    """
    Strip, collapse whitespace, and optionally truncate a string cell.

    Returns None for blank / NaN-like inputs.
    """
    if raw is None:
        return None

    s = str(raw).strip()
    if s.lower() in ("", "nan", "none", "n/a", "na", "-", "—"):
        return None

    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s)

    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip()

    return s
