"""
Tests for src/etl/loader.py
Sprint 1 · Days 02/05 — loader construction, transform logic, audit CSV.
"""
from __future__ import annotations

import csv
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.etl.loader import (
    AuditRecord,
    CompanyLoader,
    ProfitLossLoader,
    SectorLoader,
    StockPriceLoader,
    write_audit,
)
from src.utils.db import init_schema, table_counts


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Initialised empty SQLite DB in a temp directory."""
    db = tmp_path / "test.db"
    schema = Path("db/schema.sql")
    conn = sqlite3.connect(str(db))
    conn.executescript(schema.read_text())
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def sectors_xlsx(tmp_path):
    df = pd.DataFrame({"sector_name": ["Technology", "Banking", "FMCG"]})
    p = tmp_path / "sectors.xlsx"
    df.to_excel(p, index=False)
    return tmp_path


@pytest.fixture
def companies_xlsx(tmp_path):
    df = pd.DataFrame({
        "ticker": ["TCS", "INFY", "HDFCBANK"],
        "company_name": ["Tata Consultancy Services", "Infosys Ltd", "HDFC Bank Ltd"],
        "sector_name": ["Technology", "Technology", "Banking"],
        "market_cap_cr": [12000, 6000, 8000],
    })
    p = tmp_path / "companies.xlsx"
    df.to_excel(p, index=False)
    # also write sectors so FK resolves
    pd.DataFrame({"sector_name": ["Technology", "Banking"]}).to_excel(
        tmp_path / "sectors.xlsx", index=False
    )
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# AuditRecord
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditRecord:
    def test_defaults(self):
        a = AuditRecord(table_name="companies", source_file="companies.xlsx")
        assert a.rows_attempted == 0
        assert a.rows_inserted == 0
        assert a.status == "OK"

    def test_dict_contains_required_keys(self):
        a = AuditRecord("t", "f.xlsx")
        d = a.__dict__
        assert "table_name" in d
        assert "rows_rejected" in d
        assert "run_at" in d


# ─────────────────────────────────────────────────────────────────────────────
# write_audit
# ─────────────────────────────────────────────────────────────────────────────

class TestWriteAudit:
    def test_csv_written(self, tmp_path, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "OUTPUT_DIR", tmp_path)
        records = [
            AuditRecord("companies", "companies.xlsx", 92, 92, 0, "OK"),
            AuditRecord("sectors", "sectors.xlsx", 12, 12, 0, "OK"),
        ]
        out = write_audit(records)
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 2
        assert rows[0]["table_name"] == "companies"

    def test_critical_status_written(self, tmp_path, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "OUTPUT_DIR", tmp_path)
        records = [AuditRecord("bad_table", "bad.xlsx", 10, 0, 10, "CRITICAL", "file missing")]
        out = write_audit(records)
        rows = list(csv.DictReader(open(out)))
        assert rows[0]["status"] == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# SectorLoader
# ─────────────────────────────────────────────────────────────────────────────

class TestSectorLoader:
    def test_load_sectors(self, tmp_db, sectors_xlsx, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", sectors_xlsx)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        loader = SectorLoader()
        record = loader.load()
        assert record.status == "OK"
        assert record.rows_inserted == 3

    def test_dry_run_no_insert(self, tmp_db, sectors_xlsx, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", sectors_xlsx)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        loader = SectorLoader(dry_run=True)
        record = loader.load()
        assert record.notes == "DRY-RUN"
        counts = table_counts(tmp_db)
        assert counts["sectors"] == 0

    def test_missing_file_returns_critical(self, tmp_db, tmp_path, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", tmp_path)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        loader = SectorLoader()
        record = loader.load()
        assert record.status == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# CompanyLoader
# ─────────────────────────────────────────────────────────────────────────────

class TestCompanyLoader:
    def test_load_companies(self, tmp_db, companies_xlsx, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", companies_xlsx)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        # load sectors first
        SectorLoader().load()
        record = CompanyLoader().load()
        assert record.status == "OK"
        assert record.rows_inserted == 3

    def test_ticker_normalised_on_load(self, tmp_db, tmp_path, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", tmp_path)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        pd.DataFrame({"sector_name": ["Tech"]}).to_excel(tmp_path / "sectors.xlsx", index=False)
        pd.DataFrame({
            "ticker": ["tcs.ns"],
            "company_name": ["TCS"],
            "sector_name": ["Tech"],
            "market_cap_cr": [12000],
        }).to_excel(tmp_path / "companies.xlsx", index=False)
        SectorLoader().load()
        CompanyLoader().load()
        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute("SELECT ticker FROM companies WHERE ticker='TCS'").fetchone()
        conn.close()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# ProfitLossLoader
# ─────────────────────────────────────────────────────────────────────────────

class TestProfitLossLoader:
    def _setup_base(self, tmp_db, tmp_path, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", tmp_path)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        pd.DataFrame({"sector_name": ["IT"]}).to_excel(tmp_path / "sectors.xlsx", index=False)
        pd.DataFrame({
            "ticker": ["TCS"],
            "company_name": ["TCS Ltd"],
            "sector_name": ["IT"],
            "market_cap_cr": [12000],
        }).to_excel(tmp_path / "companies.xlsx", index=False)
        SectorLoader().load()
        CompanyLoader().load()

    def test_pl_insert(self, tmp_db, tmp_path, monkeypatch):
        self._setup_base(tmp_db, tmp_path, monkeypatch)
        pd.DataFrame({
            "ticker": ["TCS"],
            "fiscal_year": [2023],
            "revenue": [50000],
            "ebitda": [12000],
            "net_profit": [9000],
            "eps": [250.0],
            "opm_pct": [24.0],
            "npm_pct": [18.0],
        }).to_excel(tmp_path / "profit_and_loss.xlsx", index=False)
        record = ProfitLossLoader().load()
        assert record.rows_inserted == 1

    def test_unknown_ticker_rejected(self, tmp_db, tmp_path, monkeypatch):
        self._setup_base(tmp_db, tmp_path, monkeypatch)
        pd.DataFrame({
            "ticker": ["UNKNOWN_XYZ"],
            "fiscal_year": [2023],
            "revenue": [100],
        }).to_excel(tmp_path / "profit_and_loss.xlsx", index=False)
        record = ProfitLossLoader().load()
        assert record.rows_rejected == 1


# ─────────────────────────────────────────────────────────────────────────────
# StockPriceLoader
# ─────────────────────────────────────────────────────────────────────────────

class TestStockPriceLoader:
    def test_price_inserted(self, tmp_db, tmp_path, monkeypatch):
        from src.utils import config as cfg_mod
        monkeypatch.setattr(cfg_mod.cfg, "RAW_DATA_DIR", tmp_path)
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", tmp_db)
        pd.DataFrame({"sector_name": ["IT"]}).to_excel(tmp_path / "sectors.xlsx", index=False)
        pd.DataFrame({
            "ticker": ["TCS"],
            "company_name": ["TCS Ltd"],
            "sector_name": ["IT"],
            "market_cap_cr": [12000],
        }).to_excel(tmp_path / "companies.xlsx", index=False)
        SectorLoader().load()
        CompanyLoader().load()
        pd.DataFrame({
            "ticker": ["TCS", "TCS"],
            "date": ["2023-01-02", "2023-01-03"],
            "open": [3500, 3510],
            "high": [3550, 3560],
            "low": [3480, 3490],
            "close": [3530, 3540],
            "adj_close": [3530, 3540],
            "volume": [1000000, 900000],
        }).to_excel(tmp_path / "stock_prices.xlsx", index=False)
        record = StockPriceLoader().load()
        assert record.rows_inserted == 2


# ─────────────────────────────────────────────────────────────────────────────
# FinancialLoader.transform — year normalisation edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialLoaderTransform:
    def test_fy_prefix_normalised(self):
        loader = ProfitLossLoader.__new__(ProfitLossLoader)
        loader.dry_run = False
        loader.value_cols = ProfitLossLoader.value_cols
        df = pd.DataFrame({"ticker": ["TCS"], "fiscal_year": ["FY2023"],
                           "revenue": [50000.0]})
        result = loader._transform(df)
        assert result.iloc[0]["fiscal_year"] == 2023

    def test_range_year_normalised(self):
        loader = ProfitLossLoader.__new__(ProfitLossLoader)
        loader.dry_run = False
        loader.value_cols = ProfitLossLoader.value_cols
        df = pd.DataFrame({"ticker": ["TCS"], "fiscal_year": ["2022-23"],
                           "revenue": [50000.0]})
        result = loader._transform(df)
        assert result.iloc[0]["fiscal_year"] == 2023
