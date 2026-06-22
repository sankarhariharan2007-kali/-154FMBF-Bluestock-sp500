"""
validator.py — 16 Data Quality Rules for nifty100.db
=====================================================
Runs all DQ checks and writes output/validation_failures.csv.

Rules
-----
DQ-01  PK uniqueness — companies.ticker
DQ-02  Composite PK uniqueness — (company_id, fiscal_year) in P&L, BS, CF, ratios
DQ-03  FK integrity — all child tables reference valid company_id
DQ-04  Balance-sheet balance check — total_assets ≈ total_liabilities + total_equity (< 1%)
DQ-05  OPM cross-check — reported opm_pct vs computed (ebitda/revenue * 100)
DQ-06  Positive sales — revenue > 0
DQ-07  Date range — fiscal_year in [2000, 2030]
DQ-08  Non-null tickers — no NULL ticker in companies
DQ-09  Duplicate company names
DQ-10  Stock prices — close > 0
DQ-11  EPS sign consistency — if net_profit < 0, eps should be < 0
DQ-12  Minimum year coverage — companies with < 3 years of P&L data (WARNING)
DQ-13  Negative equity detection (WARNING)
DQ-14  Interest coverage — interest ≤ ebit (WARNING if EBIT < 0 and interest > 0)
DQ-15  Cash-flow completeness — companies with P&L but no CF data
DQ-16  Stock price completeness — companies with no price data

Severity: CRITICAL | WARNING | INFO
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.config import cfg
from src.utils.db import db_session
from src.utils.logger import logger


@dataclass
class DQFailure:
    rule_id: str
    severity: str           # CRITICAL | WARNING | INFO
    table_name: str
    column_name: str
    company_id: Any
    fiscal_year: Any
    observed_value: Any
    expected_value: Any
    description: str
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def _failures_to_csv(failures: list[DQFailure]) -> Path:
    cfg.ensure_dirs()
    out = cfg.OUTPUT_DIR / "validation_failures.csv"
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "rule_id", "severity", "table_name", "column_name",
                "company_id", "fiscal_year", "observed_value", "expected_value",
                "description", "detected_at",
            ],
        )
        writer.writeheader()
        for f in failures:
            writer.writerow(f.__dict__)
    logger.info(f"Validation failures written → {out}  ({len(failures)} rows)")
    return out


# ── Individual DQ checks ──────────────────────────────────────────────────────

def dq_01_pk_uniqueness(conn) -> list[DQFailure]:
    """DQ-01 — companies.ticker must be unique (PK enforcement)."""
    rows = conn.execute(
        "SELECT ticker, COUNT(*) AS cnt FROM companies GROUP BY ticker HAVING cnt > 1;"
    ).fetchall()
    return [
        DQFailure(
            "DQ-01", "CRITICAL", "companies", "ticker",
            None, None, f"ticker={r['ticker']} count={r['cnt']}", "count=1",
            "Duplicate ticker in companies table.",
        )
        for r in rows
    ]


def dq_02_composite_pk(conn) -> list[DQFailure]:
    """DQ-02 — (company_id, fiscal_year) PK in financial tables."""
    failures = []
    for tbl in ("profitandloss", "balancesheet", "cashflow", "financial_ratios"):
        try:
            rows = conn.execute(
                f"""
                SELECT company_id, fiscal_year, COUNT(*) AS cnt
                FROM {tbl}
                GROUP BY company_id, fiscal_year
                HAVING cnt > 1;
                """
            ).fetchall()
            for r in rows:
                failures.append(DQFailure(
                    "DQ-02", "CRITICAL", tbl, "(company_id, fiscal_year)",
                    r["company_id"], r["fiscal_year"],
                    f"count={r['cnt']}", "count=1",
                    f"Duplicate (company_id, fiscal_year) in {tbl}.",
                ))
        except Exception as exc:
            logger.warning(f"DQ-02 skipped for {tbl}: {exc}")
    return failures


def dq_03_fk_integrity(conn) -> list[DQFailure]:
    """DQ-03 — PRAGMA foreign_key_check."""
    rows = conn.execute("PRAGMA foreign_key_check;").fetchall()
    return [
        DQFailure(
            "DQ-03", "CRITICAL", str(r[0]), "foreign_key",
            None, None, str(dict(r)), "valid FK",
            "Foreign key violation detected.",
        )
        for r in rows
    ]


def dq_04_bs_balance(conn) -> list[DQFailure]:
    """DQ-04 — total_assets ≈ total_liabilities + total_equity (<1% tolerance)."""
    failures = []
    try:
        rows = conn.execute(
            """
            SELECT company_id, fiscal_year, total_assets, total_liabilities, total_equity
            FROM balancesheet
            WHERE total_assets IS NOT NULL
              AND total_liabilities IS NOT NULL
              AND total_equity IS NOT NULL
              AND total_assets != 0;
            """
        ).fetchall()
        for r in rows:
            computed = (r["total_liabilities"] or 0) + (r["total_equity"] or 0)
            if computed == 0:
                continue
            diff_pct = abs(r["total_assets"] - computed) / abs(computed) * 100
            if diff_pct > 1.0:
                failures.append(DQFailure(
                    "DQ-04", "WARNING", "balancesheet", "total_assets",
                    r["company_id"], r["fiscal_year"],
                    f"{r['total_assets']:.2f}",
                    f"≈{computed:.2f} (diff {diff_pct:.2f}%)",
                    "Balance-sheet imbalance > 1%.",
                ))
    except Exception as exc:
        logger.warning(f"DQ-04 skipped: {exc}")
    return failures


def dq_05_opm_crosscheck(conn) -> list[DQFailure]:
    """DQ-05 — reported opm_pct vs computed EBITDA/revenue * 100 (tolerance 2pp)."""
    failures = []
    try:
        rows = conn.execute(
            """
            SELECT company_id, fiscal_year, opm_pct, ebitda, revenue
            FROM profitandloss
            WHERE opm_pct IS NOT NULL AND ebitda IS NOT NULL
              AND revenue IS NOT NULL AND revenue != 0;
            """
        ).fetchall()
        for r in rows:
            computed_opm = r["ebitda"] / r["revenue"] * 100
            diff = abs((r["opm_pct"] or 0) - computed_opm)
            if diff > 2.0:
                failures.append(DQFailure(
                    "DQ-05", "WARNING", "profitandloss", "opm_pct",
                    r["company_id"], r["fiscal_year"],
                    f"{r['opm_pct']:.2f}%",
                    f"≈{computed_opm:.2f}% (diff {diff:.2f}pp)",
                    "Reported OPM deviates > 2pp from computed EBITDA/Revenue.",
                ))
    except Exception as exc:
        logger.warning(f"DQ-05 skipped: {exc}")
    return failures


def dq_06_positive_sales(conn) -> list[DQFailure]:
    """DQ-06 — revenue must be > 0."""
    failures = []
    try:
        rows = conn.execute(
            """
            SELECT company_id, fiscal_year, revenue
            FROM profitandloss
            WHERE revenue IS NOT NULL AND revenue <= 0;
            """
        ).fetchall()
        for r in rows:
            failures.append(DQFailure(
                "DQ-06", "WARNING", "profitandloss", "revenue",
                r["company_id"], r["fiscal_year"],
                str(r["revenue"]), "> 0",
                "Revenue is zero or negative.",
            ))
    except Exception as exc:
        logger.warning(f"DQ-06 skipped: {exc}")
    return failures


def dq_07_year_range(conn) -> list[DQFailure]:
    """DQ-07 — fiscal_year must be in [2000, 2030]."""
    failures = []
    for tbl in ("profitandloss", "balancesheet", "cashflow"):
        try:
            rows = conn.execute(
                f"""
                SELECT company_id, fiscal_year FROM {tbl}
                WHERE fiscal_year IS NOT NULL
                  AND (fiscal_year < 2000 OR fiscal_year > 2030);
                """
            ).fetchall()
            for r in rows:
                failures.append(DQFailure(
                    "DQ-07", "CRITICAL", tbl, "fiscal_year",
                    r["company_id"], r["fiscal_year"],
                    str(r["fiscal_year"]), "[2000, 2030]",
                    "fiscal_year out of expected range.",
                ))
        except Exception as exc:
            logger.warning(f"DQ-07 skipped for {tbl}: {exc}")
    return failures


def dq_08_non_null_tickers(conn) -> list[DQFailure]:
    """DQ-08 — no NULL ticker in companies."""
    try:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM companies WHERE ticker IS NULL OR ticker = '';"
        ).fetchone()[0]
    except Exception:
        return []
    if cnt > 0:
        return [DQFailure(
            "DQ-08", "CRITICAL", "companies", "ticker",
            None, None, f"NULL count={cnt}", "0",
            "NULL or empty tickers found in companies.",
        )]
    return []


def dq_09_duplicate_company_names(conn) -> list[DQFailure]:
    """DQ-09 — duplicate company names (WARNING — may be intentional ADR/subsidiary)."""
    try:
        rows = conn.execute(
            """
            SELECT company_name, COUNT(*) cnt
            FROM companies
            GROUP BY LOWER(TRIM(company_name))
            HAVING cnt > 1;
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-09", "WARNING", "companies", "company_name",
            None, None, f"'{r['company_name']}' count={r['cnt']}", "count=1",
            "Duplicate company name detected.",
        )
        for r in rows
    ]


def dq_10_positive_close_price(conn) -> list[DQFailure]:
    """DQ-10 — stock close price must be > 0."""
    try:
        rows = conn.execute(
            """
            SELECT company_id, price_date, close
            FROM stock_prices
            WHERE close IS NOT NULL AND close <= 0
            LIMIT 50;
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-10", "WARNING", "stock_prices", "close",
            r["company_id"], r["price_date"],
            str(r["close"]), "> 0",
            "Stock close price is zero or negative.",
        )
        for r in rows
    ]


def dq_11_eps_sign_consistency(conn) -> list[DQFailure]:
    """DQ-11 — if net_profit < 0, eps should also be < 0."""
    try:
        rows = conn.execute(
            """
            SELECT company_id, fiscal_year, net_profit, eps
            FROM profitandloss
            WHERE net_profit < 0 AND eps > 0
               OR net_profit > 0 AND eps < 0;
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-11", "WARNING", "profitandloss", "eps",
            r["company_id"], r["fiscal_year"],
            f"eps={r['eps']}", f"same sign as net_profit={r['net_profit']}",
            "EPS sign inconsistent with net_profit sign.",
        )
        for r in rows
    ]


def dq_12_min_year_coverage(conn) -> list[DQFailure]:
    """DQ-12 — companies with < 3 years of P&L data (WARNING)."""
    try:
        rows = conn.execute(
            """
            SELECT c.company_id, c.ticker, COUNT(DISTINCT pl.fiscal_year) AS yr_cnt
            FROM companies c
            LEFT JOIN profitandloss pl USING (company_id)
            GROUP BY c.company_id
            HAVING yr_cnt < 3;
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-12", "WARNING", "profitandloss", "fiscal_year",
            r["company_id"], None,
            f"years={r['yr_cnt']}", ">= 3",
            f"Company {r['ticker']} has fewer than 3 years of P&L data.",
        )
        for r in rows
    ]


def dq_13_negative_equity(conn) -> list[DQFailure]:
    """DQ-13 — negative total_equity detection."""
    try:
        rows = conn.execute(
            """
            SELECT company_id, fiscal_year, total_equity
            FROM balancesheet
            WHERE total_equity IS NOT NULL AND total_equity < 0;
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-13", "WARNING", "balancesheet", "total_equity",
            r["company_id"], r["fiscal_year"],
            str(r["total_equity"]), ">= 0",
            "Negative equity detected — may indicate distressed company.",
        )
        for r in rows
    ]


def dq_14_interest_coverage(conn) -> list[DQFailure]:
    """DQ-14 — interest > ebit when ebit < 0 (interest coverage < 1)."""
    try:
        rows = conn.execute(
            """
            SELECT company_id, fiscal_year, ebit, interest
            FROM profitandloss
            WHERE ebit IS NOT NULL AND interest IS NOT NULL
              AND ebit < 0 AND interest > 0;
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-14", "WARNING", "profitandloss", "interest",
            r["company_id"], r["fiscal_year"],
            f"ebit={r['ebit']} interest={r['interest']}", "interest <= ebit",
            "Negative EBIT with positive interest — potential default risk.",
        )
        for r in rows
    ]


def dq_15_cashflow_completeness(conn) -> list[DQFailure]:
    """DQ-15 — companies with P&L but missing CF data."""
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT pl.company_id
            FROM profitandloss pl
            WHERE pl.company_id NOT IN (SELECT DISTINCT company_id FROM cashflow);
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-15", "WARNING", "cashflow", "company_id",
            r["company_id"], None,
            "no rows", "CF data present",
            "Company has P&L data but no cash-flow data.",
        )
        for r in rows
    ]


def dq_16_price_completeness(conn) -> list[DQFailure]:
    """DQ-16 — companies with no stock price data."""
    try:
        rows = conn.execute(
            """
            SELECT company_id, ticker
            FROM companies
            WHERE company_id NOT IN (SELECT DISTINCT company_id FROM stock_prices);
            """
        ).fetchall()
    except Exception:
        return []
    return [
        DQFailure(
            "DQ-16", "WARNING", "stock_prices", "company_id",
            r["company_id"], None,
            "no price rows", "price data present",
            f"Company {r['ticker']} has no stock price data.",
        )
        for r in rows
    ]


# ── Runner ────────────────────────────────────────────────────────────────────

ALL_RULES = [
    dq_01_pk_uniqueness,
    dq_02_composite_pk,
    dq_03_fk_integrity,
    dq_04_bs_balance,
    dq_05_opm_crosscheck,
    dq_06_positive_sales,
    dq_07_year_range,
    dq_08_non_null_tickers,
    dq_09_duplicate_company_names,
    dq_10_positive_close_price,
    dq_11_eps_sign_consistency,
    dq_12_min_year_coverage,
    dq_13_negative_equity,
    dq_14_interest_coverage,
    dq_15_cashflow_completeness,
    dq_16_price_completeness,
]


def run_all_rules(db_path=None) -> list[DQFailure]:
    all_failures: list[DQFailure] = []
    with db_session(db_path, commit=False) as conn:
        for rule_fn in ALL_RULES:
            rule_id = rule_fn.__name__[:5].upper()
            logger.info(f"Running {rule_fn.__doc__.split('—')[0].strip()} …")
            try:
                failures = rule_fn(conn)
                critical = [f for f in failures if f.severity == "CRITICAL"]
                warnings = [f for f in failures if f.severity == "WARNING"]
                logger.info(
                    f"  → {rule_fn.__name__}: {len(critical)} CRITICAL, {len(warnings)} WARNING"
                )
                all_failures.extend(failures)
            except Exception as exc:
                logger.error(f"  → {rule_fn.__name__} ERROR: {exc}")

    _failures_to_csv(all_failures)

    critical_total = sum(1 for f in all_failures if f.severity == "CRITICAL")
    warning_total  = sum(1 for f in all_failures if f.severity == "WARNING")
    logger.info(
        f"\n{'═'*50}\n"
        f"DQ Summary: {len(ALL_RULES)} rules | "
        f"{critical_total} CRITICAL | {warning_total} WARNING\n"
        f"{'═'*50}"
    )
    return all_failures


if __name__ == "__main__":
    run_all_rules()
