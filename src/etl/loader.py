"""
loader.py — Nifty-100 Analytics ETL Loader
============================================
Loads all 12 source Excel files into nifty100.db.
Produces output/load_audit.csv on completion.

Usage (CLI)
-----------
python -m src.etl.loader --all              # load all files
python -m src.etl.loader --table companies  # load one table
python -m src.etl.loader --dry-run          # parse only, no DB writes
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.etl.normaliser import (
    clean_string,
    normalize_column_name,
    normalize_numeric,
    normalize_ticker,
    normalize_year,
)
from src.utils.config import cfg
from src.utils.db import db_session, init_schema
from src.utils.logger import logger


# ── Audit record ─────────────────────────────────────────────────────────────

@dataclass
class AuditRecord:
    table_name: str
    source_file: str
    rows_attempted: int = 0
    rows_inserted: int = 0
    rows_rejected: int = 0
    status: str = "OK"              # OK | WARNING | CRITICAL
    notes: str = ""
    run_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── Base loader ───────────────────────────────────────────────────────────────

class BaseLoader:
    """Abstract base for table-specific loaders."""

    table_name: str = ""
    source_file: str = ""          # filename inside RAW_DATA_DIR

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.audit = AuditRecord(table_name=self.table_name, source_file=self.source_file)

    # ── Subclasses override this ──────────────────────────────────────────────
    def _read_raw(self) -> pd.DataFrame:
        path = cfg.RAW_DATA_DIR / self.source_file
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")
        logger.info(f"Reading {path}")
        df = pd.read_excel(path, engine="openpyxl")
        df.columns = [normalize_column_name(c) for c in df.columns]
        return df

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Override to apply table-specific transformations."""
        return df

    def _insert_row(self, conn: Any, row: dict) -> bool:
        """Override to perform the INSERT. Return True on success."""
        raise NotImplementedError

    # ── Orchestration ─────────────────────────────────────────────────────────
    def load(self) -> AuditRecord:
        logger.info(f"[{self.table_name}] Starting load from {self.source_file}")
        try:
            df = self._read_raw()
        except FileNotFoundError as exc:
            logger.error(str(exc))
            self.audit.status = "CRITICAL"
            self.audit.notes = str(exc)
            return self.audit

        df = self._transform(df)
        self.audit.rows_attempted = len(df)

        if self.dry_run:
            logger.info(f"[{self.table_name}] DRY-RUN: {len(df)} rows parsed, no DB writes.")
            self.audit.status = "OK"
            self.audit.notes = "DRY-RUN"
            return self.audit

        with db_session() as conn:
            for _, row in df.iterrows():
                try:
                    ok = self._insert_row(conn, row.to_dict())
                    if ok:
                        self.audit.rows_inserted += 1
                    else:
                        self.audit.rows_rejected += 1
                except Exception as exc:
                    logger.warning(f"[{self.table_name}] Row rejected: {exc}")
                    self.audit.rows_rejected += 1

        if self.audit.rows_rejected > 0:
            reject_pct = self.audit.rows_rejected / max(self.audit.rows_attempted, 1)
            self.audit.status = "CRITICAL" if reject_pct > 0.05 else "WARNING"

        logger.info(
            f"[{self.table_name}] Done — inserted={self.audit.rows_inserted} "
            f"rejected={self.audit.rows_rejected} status={self.audit.status}"
        )
        return self.audit


# ── Concrete loaders ──────────────────────────────────────────────────────────

class SectorLoader(BaseLoader):
    table_name = "sectors"
    source_file = "sectors.xlsx"

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns={"sector": "sector_name", "name": "sector_name"}, errors="ignore")
        df["sector_name"] = df["sector_name"].apply(clean_string)
        df = df.dropna(subset=["sector_name"]).drop_duplicates(subset=["sector_name"])
        return df

    def _insert_row(self, conn, row):
        conn.execute(
            "INSERT OR IGNORE INTO sectors (sector_name) VALUES (?);",
            (row["sector_name"],),
        )
        return True


class CompanyLoader(BaseLoader):
    table_name = "companies"
    source_file = "companies.xlsx"

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df["ticker"] = df.get("ticker", df.get("symbol", pd.Series(dtype=str))).apply(
            lambda x: normalize_ticker(x) if pd.notna(x) else None
        )
        df["company_name"] = df.get(
            "company_name", df.get("name", pd.Series(dtype=str))
        ).apply(clean_string)
        df["sector_name"] = df.get("sector_name", df.get("sector", pd.Series(dtype=str))).apply(
            clean_string
        )
        df["market_cap_cr"] = df.get("market_cap_cr", pd.Series(dtype=float)).apply(
            normalize_numeric
        )
        df = df.dropna(subset=["ticker", "company_name"])
        return df

    def _insert_row(self, conn, row):
        # Resolve sector_id
        sector_id = None
        if row.get("sector_name"):
            res = conn.execute(
                "SELECT sector_id FROM sectors WHERE sector_name = ?;", (row["sector_name"],)
            ).fetchone()
            if res:
                sector_id = res[0]

        conn.execute(
            """
            INSERT OR IGNORE INTO companies (ticker, company_name, sector_id, market_cap_cr)
            VALUES (?, ?, ?, ?);
            """,
            (row["ticker"], row["company_name"], sector_id, row.get("market_cap_cr")),
        )
        return True


class FinancialLoader(BaseLoader):
    """Generic loader for P&L, BS, CF tables that share (company_id, fiscal_year) PK."""

    # Subclasses set these
    table_name = ""
    source_file = ""
    insert_sql = ""
    value_cols: list[str] = []

    def _resolve_company_id(self, conn, ticker: str) -> int | None:
        row = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (ticker,)
        ).fetchone()
        return row[0] if row else None

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        # Expect 'ticker' or 'symbol' + year columns
        if "ticker" not in df.columns and "symbol" in df.columns:
            df = df.rename(columns={"symbol": "ticker"})
        df["ticker"] = df["ticker"].apply(lambda x: normalize_ticker(x) if pd.notna(x) else None)
        df["fiscal_year"] = df.get("fiscal_year", df.get("year", pd.Series(dtype=object))).apply(
            lambda x: normalize_year(x) if pd.notna(x) else None
        )
        for col in self.value_cols:
            if col in df.columns:
                df[col] = df[col].apply(normalize_numeric)
        df = df.dropna(subset=["ticker", "fiscal_year"])
        return df

    def _insert_row(self, conn, row):
        with db_session.__func__.__closure__:  # access conn directly
            pass
        return True   # overridden below per table


class ProfitLossLoader(FinancialLoader):
    table_name = "profitandloss"
    source_file = "profit_and_loss.xlsx"
    value_cols = [
        "revenue", "other_income", "total_income", "expenses",
        "ebitda", "depreciation", "ebit", "interest",
        "pbt", "tax", "net_profit", "eps", "opm_pct", "npm_pct",
    ]

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT OR IGNORE INTO profitandloss
              (company_id, fiscal_year, revenue, other_income, total_income, expenses,
               ebitda, depreciation, ebit, interest, pbt, tax, net_profit, eps, opm_pct, npm_pct)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                cid[0], row["fiscal_year"],
                row.get("revenue"), row.get("other_income"), row.get("total_income"),
                row.get("expenses"), row.get("ebitda"), row.get("depreciation"),
                row.get("ebit"), row.get("interest"), row.get("pbt"), row.get("tax"),
                row.get("net_profit"), row.get("eps"), row.get("opm_pct"), row.get("npm_pct"),
            ),
        )
        return True


class BalanceSheetLoader(FinancialLoader):
    table_name = "balancesheet"
    source_file = "balance_sheet.xlsx"
    value_cols = [
        "share_capital", "reserves", "total_equity", "long_term_debt",
        "short_term_debt", "total_borrowings", "total_liabilities",
        "fixed_assets", "cwip", "investments", "current_assets",
        "current_liabilities", "total_assets",
    ]

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT OR IGNORE INTO balancesheet
              (company_id, fiscal_year, share_capital, reserves, total_equity,
               long_term_debt, short_term_debt, total_borrowings, total_liabilities,
               fixed_assets, cwip, investments, current_assets, current_liabilities, total_assets)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                cid[0], row["fiscal_year"],
                row.get("share_capital"), row.get("reserves"), row.get("total_equity"),
                row.get("long_term_debt"), row.get("short_term_debt"), row.get("total_borrowings"),
                row.get("total_liabilities"), row.get("fixed_assets"), row.get("cwip"),
                row.get("investments"), row.get("current_assets"),
                row.get("current_liabilities"), row.get("total_assets"),
            ),
        )
        return True


class CashFlowLoader(FinancialLoader):
    table_name = "cashflow"
    source_file = "cash_flow.xlsx"
    value_cols = ["cfo", "cfi", "cff", "net_cash_flow", "capex", "free_cash_flow"]

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT OR IGNORE INTO cashflow
              (company_id, fiscal_year, cfo, cfi, cff, net_cash_flow, capex, free_cash_flow)
            VALUES (?,?,?,?,?,?,?,?);
            """,
            (
                cid[0], row["fiscal_year"],
                row.get("cfo"), row.get("cfi"), row.get("cff"),
                row.get("net_cash_flow"), row.get("capex"), row.get("free_cash_flow"),
            ),
        )
        return True


class StockPriceLoader(BaseLoader):
    table_name = "stock_prices"
    source_file = "stock_prices.xlsx"

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if "ticker" not in df.columns and "symbol" in df.columns:
            df = df.rename(columns={"symbol": "ticker"})
        df["ticker"] = df["ticker"].apply(lambda x: normalize_ticker(x) if pd.notna(x) else None)
        df["price_date"] = pd.to_datetime(df.get("date", df.get("price_date")), errors="coerce").dt.strftime("%Y-%m-%d")
        for col in ["open", "high", "low", "close", "adj_close"]:
            if col in df.columns:
                df[col] = df[col].apply(normalize_numeric)
        df["volume"] = pd.to_numeric(df.get("volume", pd.Series(dtype=float)), errors="coerce").fillna(0).astype(int)
        df = df.dropna(subset=["ticker", "price_date"])
        return df

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT OR IGNORE INTO stock_prices
              (company_id, price_date, open, high, low, close, volume, adj_close)
            VALUES (?,?,?,?,?,?,?,?);
            """,
            (
                cid[0], row["price_date"],
                row.get("open"), row.get("high"), row.get("low"),
                row.get("close"), row.get("volume", 0), row.get("adj_close"),
            ),
        )
        return True


class FinancialRatiosLoader(FinancialLoader):
    table_name = "financial_ratios"
    source_file = "financial_ratios.xlsx"
    value_cols = [
        "pe_ratio", "pb_ratio", "ev_ebitda", "roe_pct", "roce_pct",
        "debt_equity", "current_ratio", "quick_ratio", "dividend_yield_pct",
    ]

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT OR IGNORE INTO financial_ratios
              (company_id, fiscal_year, pe_ratio, pb_ratio, ev_ebitda, roe_pct, roce_pct,
               debt_equity, current_ratio, quick_ratio, dividend_yield_pct)
            VALUES (?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                cid[0], row["fiscal_year"],
                row.get("pe_ratio"), row.get("pb_ratio"), row.get("ev_ebitda"),
                row.get("roe_pct"), row.get("roce_pct"), row.get("debt_equity"),
                row.get("current_ratio"), row.get("quick_ratio"), row.get("dividend_yield_pct"),
            ),
        )
        return True


class AnalysisLoader(FinancialLoader):
    table_name = "analysis"
    source_file = "analysis.xlsx"
    value_cols = ["target_price", "upside_pct"]

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT OR IGNORE INTO analysis
              (company_id, fiscal_year, analyst_rating, target_price, upside_pct, risk_level, notes)
            VALUES (?,?,?,?,?,?,?);
            """,
            (
                cid[0], row.get("fiscal_year"),
                clean_string(row.get("analyst_rating")), row.get("target_price"),
                row.get("upside_pct"), clean_string(row.get("risk_level")),
                clean_string(row.get("notes")),
            ),
        )
        return True


class DocumentsLoader(BaseLoader):
    table_name = "documents"
    source_file = "documents.xlsx"

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if "ticker" not in df.columns and "symbol" in df.columns:
            df = df.rename(columns={"symbol": "ticker"})
        df["ticker"] = df["ticker"].apply(lambda x: normalize_ticker(x) if pd.notna(x) else None)
        df["fiscal_year"] = df.get("fiscal_year", df.get("year", pd.Series(dtype=object))).apply(
            lambda x: normalize_year(x) if pd.notna(x) else None
        )
        df = df.dropna(subset=["ticker"])
        return df

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT INTO documents (company_id, doc_type, fiscal_year, title, url, source_file)
            VALUES (?,?,?,?,?,?);
            """,
            (
                cid[0],
                clean_string(row.get("doc_type", "Unknown")),
                row.get("fiscal_year"),
                clean_string(row.get("title")),
                clean_string(row.get("url")),
                self.source_file,
            ),
        )
        return True


class ProsConsLoader(BaseLoader):
    table_name = "prosandcons"
    source_file = "prosandcons.xlsx"

    def _transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if "ticker" not in df.columns and "symbol" in df.columns:
            df = df.rename(columns={"symbol": "ticker"})
        df["ticker"] = df["ticker"].apply(lambda x: normalize_ticker(x) if pd.notna(x) else None)
        df["type"] = df.get("type", df.get("category", pd.Series(dtype=str))).str.upper().str.strip()
        df["type"] = df["type"].where(df["type"].isin(["PRO", "CON"]), "PRO")
        df = df.dropna(subset=["ticker", "description"] if "description" in df.columns else ["ticker"])
        return df

    def _insert_row(self, conn, row):
        cid = conn.execute(
            "SELECT company_id FROM companies WHERE ticker = ?;", (row["ticker"],)
        ).fetchone()
        if not cid:
            return False
        conn.execute(
            """
            INSERT INTO prosandcons (company_id, type, description, fiscal_year)
            VALUES (?,?,?,?);
            """,
            (
                cid[0],
                row.get("type", "PRO"),
                clean_string(row.get("description", row.get("text", ""))),
                row.get("fiscal_year"),
            ),
        )
        return True


# ── Load order (respects FK dependencies) ─────────────────────────────────────

LOAD_ORDER: list[type[BaseLoader]] = [
    SectorLoader,
    CompanyLoader,
    ProfitLossLoader,
    BalanceSheetLoader,
    CashFlowLoader,
    FinancialRatiosLoader,
    StockPriceLoader,
    AnalysisLoader,
    DocumentsLoader,
    ProsConsLoader,
]


# ── Audit writer ──────────────────────────────────────────────────────────────

def write_audit(records: list[AuditRecord]) -> Path:
    cfg.ensure_dirs()
    out = cfg.OUTPUT_DIR / "load_audit.csv"
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "table_name", "source_file", "rows_attempted",
                "rows_inserted", "rows_rejected", "status", "notes", "run_at",
            ],
        )
        writer.writeheader()
        for r in records:
            writer.writerow(r.__dict__)
    logger.info(f"Audit written → {out}")
    return out


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nifty-100 ETL Loader")
    parser.add_argument("--all", action="store_true", help="Load all tables")
    parser.add_argument("--table", type=str, help="Load a specific table by name")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    parser.add_argument("--init-schema", action="store_true", help="(Re-)initialise DB schema first")
    args = parser.parse_args(argv)

    cfg.ensure_dirs()

    if args.init_schema:
        init_schema()

    loaders_to_run: list[type[BaseLoader]]
    if args.all:
        loaders_to_run = LOAD_ORDER
    elif args.table:
        loaders_to_run = [cls for cls in LOAD_ORDER if cls.table_name == args.table]
        if not loaders_to_run:
            logger.error(f"Unknown table: {args.table}")
            return 1
    else:
        parser.print_help()
        return 0

    records: list[AuditRecord] = []
    for Loader in loaders_to_run:
        instance = Loader(dry_run=args.dry_run)
        record = instance.load()
        records.append(record)

    write_audit(records)

    critical = [r for r in records if r.status == "CRITICAL"]
    if critical:
        logger.error(f"{len(critical)} CRITICAL failures — see load_audit.csv")
        return 1

    logger.info("All loads completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
