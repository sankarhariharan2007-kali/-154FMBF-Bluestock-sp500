"""
Tests for src/etl/validator.py — 16 DQ rules
Sprint 1 · Day 03
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.etl.validator import (
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
    DQFailure,
    run_all_rules,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_conn(tmp_path):
    """SQLite connection with schema applied and FK on."""
    db = tmp_path / "dq_test.db"
    schema = Path("db/schema.sql")
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(schema.read_text())
    yield conn
    conn.close()


def _add_sector(conn, name="IT"):
    conn.execute("INSERT INTO sectors (sector_name) VALUES (?);", (name,))
    return conn.execute("SELECT sector_id FROM sectors WHERE sector_name=?;", (name,)).fetchone()[0]


def _add_company(conn, ticker="TCS", name="TCS Ltd", sector_id=None):
    conn.execute(
        "INSERT INTO companies (ticker, company_name, sector_id) VALUES (?,?,?);",
        (ticker, name, sector_id),
    )
    return conn.execute(
        "SELECT company_id FROM companies WHERE ticker=?;", (ticker,)
    ).fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# DQ-01
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ01:
    def test_no_duplicates(self, fresh_conn):
        _add_company(fresh_conn, "TCS")
        _add_company(fresh_conn, "INFY")
        fresh_conn.commit()
        assert dq_01_pk_uniqueness(fresh_conn) == []

    def test_schema_enforces_unique(self, fresh_conn):
        _add_company(fresh_conn, "TCS")
        fresh_conn.commit()
        with pytest.raises(Exception):
            _add_company(fresh_conn, "TCS")  # UNIQUE constraint violation


# ─────────────────────────────────────────────────────────────────────────────
# DQ-02
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ02:
    def test_no_composite_pk_violations(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, revenue) VALUES (?,?,?);",
            (cid, 2023, 50000),
        )
        fresh_conn.commit()
        assert dq_02_composite_pk(fresh_conn) == []

    def test_schema_enforces_composite_unique(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, revenue) VALUES (?,?,?);",
            (cid, 2023, 50000),
        )
        fresh_conn.commit()
        with pytest.raises(Exception):
            fresh_conn.execute(
                "INSERT INTO profitandloss (company_id, fiscal_year, revenue) VALUES (?,?,?);",
                (cid, 2023, 60000),
            )
            fresh_conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# DQ-03
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ03:
    def test_no_fk_violations(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year) VALUES (?,?);", (cid, 2023)
        )
        fresh_conn.commit()
        assert dq_03_fk_integrity(fresh_conn) == []


# ─────────────────────────────────────────────────────────────────────────────
# DQ-04
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ04:
    def test_balanced_sheet_passes(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            """INSERT INTO balancesheet
               (company_id, fiscal_year, total_assets, total_liabilities, total_equity)
               VALUES (?,?,?,?,?);""",
            (cid, 2023, 100000, 40000, 60000),
        )
        fresh_conn.commit()
        assert dq_04_bs_balance(fresh_conn) == []

    def test_imbalanced_sheet_fails(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            """INSERT INTO balancesheet
               (company_id, fiscal_year, total_assets, total_liabilities, total_equity)
               VALUES (?,?,?,?,?);""",
            (cid, 2023, 100000, 30000, 50000),  # 20% imbalance
        )
        fresh_conn.commit()
        failures = dq_04_bs_balance(fresh_conn)
        assert len(failures) == 1
        assert failures[0].severity == "WARNING"


# ─────────────────────────────────────────────────────────────────────────────
# DQ-05
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ05:
    def test_opm_within_tolerance(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            """INSERT INTO profitandloss
               (company_id, fiscal_year, revenue, ebitda, opm_pct)
               VALUES (?,?,?,?,?);""",
            (cid, 2023, 10000, 2500, 25.0),  # exact match
        )
        fresh_conn.commit()
        assert dq_05_opm_crosscheck(fresh_conn) == []

    def test_opm_deviation_flags(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            """INSERT INTO profitandloss
               (company_id, fiscal_year, revenue, ebitda, opm_pct)
               VALUES (?,?,?,?,?);""",
            (cid, 2023, 10000, 2500, 10.0),  # 15pp deviation
        )
        fresh_conn.commit()
        failures = dq_05_opm_crosscheck(fresh_conn)
        assert len(failures) == 1


# ─────────────────────────────────────────────────────────────────────────────
# DQ-06
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ06:
    def test_positive_revenue_passes(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, revenue) VALUES (?,?,?);",
            (cid, 2023, 50000),
        )
        fresh_conn.commit()
        assert dq_06_positive_sales(fresh_conn) == []

    def test_zero_revenue_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, revenue) VALUES (?,?,?);",
            (cid, 2023, 0),
        )
        fresh_conn.commit()
        assert len(dq_06_positive_sales(fresh_conn)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# DQ-07
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ07:
    def test_valid_year_passes(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year) VALUES (?,?);", (cid, 2023)
        )
        fresh_conn.commit()
        assert dq_07_year_range(fresh_conn) == []

    def test_out_of_range_year_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        # Use raw INSERT to bypass normaliser
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year) VALUES (?,?);", (cid, 1980)
        )
        fresh_conn.commit()
        failures = dq_07_year_range(fresh_conn)
        assert len(failures) == 1
        assert failures[0].severity == "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# DQ-08
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ08:
    def test_all_tickers_present(self, fresh_conn):
        _add_company(fresh_conn, "TCS")
        fresh_conn.commit()
        assert dq_08_non_null_tickers(fresh_conn) == []


# ─────────────────────────────────────────────────────────────────────────────
# DQ-09
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ09:
    def test_no_duplicate_names(self, fresh_conn):
        _add_company(fresh_conn, "TCS", "TCS Ltd")
        _add_company(fresh_conn, "INFY", "Infosys Ltd")
        fresh_conn.commit()
        assert dq_09_duplicate_company_names(fresh_conn) == []

    def test_duplicate_name_flagged(self, fresh_conn):
        _add_company(fresh_conn, "TCS", "TCS Ltd")
        _add_company(fresh_conn, "TCS2", "TCS Ltd")  # same name different ticker
        fresh_conn.commit()
        failures = dq_09_duplicate_company_names(fresh_conn)
        assert len(failures) == 1
        assert failures[0].severity == "WARNING"


# ─────────────────────────────────────────────────────────────────────────────
# DQ-10
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ10:
    def test_positive_close_passes(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO stock_prices (company_id, price_date, close) VALUES (?,?,?);",
            (cid, "2023-01-02", 3500.0),
        )
        fresh_conn.commit()
        assert dq_10_positive_close_price(fresh_conn) == []

    def test_zero_close_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO stock_prices (company_id, price_date, close) VALUES (?,?,?);",
            (cid, "2023-01-02", 0.0),
        )
        fresh_conn.commit()
        failures = dq_10_positive_close_price(fresh_conn)
        assert len(failures) == 1


# ─────────────────────────────────────────────────────────────────────────────
# DQ-11
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ11:
    def test_consistent_sign_passes(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, net_profit, eps) VALUES (?,?,?,?);",
            (cid, 2023, -500, -12.5),
        )
        fresh_conn.commit()
        assert dq_11_eps_sign_consistency(fresh_conn) == []

    def test_inconsistent_sign_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, net_profit, eps) VALUES (?,?,?,?);",
            (cid, 2023, -500, 12.5),  # loss but positive EPS
        )
        fresh_conn.commit()
        assert len(dq_11_eps_sign_consistency(fresh_conn)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# DQ-12
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ12:
    def test_sufficient_years_passes(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        for yr in [2021, 2022, 2023]:
            fresh_conn.execute(
                "INSERT INTO profitandloss (company_id, fiscal_year) VALUES (?,?);", (cid, yr)
            )
        fresh_conn.commit()
        assert dq_12_min_year_coverage(fresh_conn) == []

    def test_insufficient_years_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "NEWCO")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year) VALUES (?,?);", (cid, 2023)
        )
        fresh_conn.commit()
        failures = dq_12_min_year_coverage(fresh_conn)
        assert any(f.company_id == cid for f in failures)


# ─────────────────────────────────────────────────────────────────────────────
# DQ-13 through DQ-16 — smoke tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDQ13to16:
    def test_dq13_negative_equity_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO balancesheet (company_id, fiscal_year, total_equity) VALUES (?,?,?);",
            (cid, 2023, -100),
        )
        fresh_conn.commit()
        failures = dq_13_negative_equity(fresh_conn)
        assert len(failures) == 1
        assert failures[0].severity == "WARNING"

    def test_dq14_interest_coverage_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year, ebit, interest) VALUES (?,?,?,?);",
            (cid, 2023, -500, 200),
        )
        fresh_conn.commit()
        assert len(dq_14_interest_coverage(fresh_conn)) == 1

    def test_dq15_missing_cf_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.execute(
            "INSERT INTO profitandloss (company_id, fiscal_year) VALUES (?,?);", (cid, 2023)
        )
        fresh_conn.commit()
        failures = dq_15_cashflow_completeness(fresh_conn)
        assert any(f.company_id == cid for f in failures)

    def test_dq16_missing_price_flagged(self, fresh_conn):
        cid = _add_company(fresh_conn, "TCS")
        fresh_conn.commit()
        failures = dq_16_price_completeness(fresh_conn)
        assert any(f.company_id == cid for f in failures)


# ─────────────────────────────────────────────────────────────────────────────
# run_all_rules — integration smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestRunAllRules:
    def test_run_on_clean_db(self, tmp_path, monkeypatch):
        """run_all_rules on an empty schema-applied DB should produce no CRITICAL."""
        from src.utils import config as cfg_mod
        db = tmp_path / "clean.db"
        schema = Path("db/schema.sql")
        conn = sqlite3.connect(str(db))
        conn.executescript(schema.read_text())
        conn.commit(); conn.close()
        monkeypatch.setattr(cfg_mod.cfg, "DB_PATH", db)
        monkeypatch.setattr(cfg_mod.cfg, "OUTPUT_DIR", tmp_path)
        failures = run_all_rules(db)
        critical = [f for f in failures if f.severity == "CRITICAL"]
        assert critical == []

    def test_dqfailure_dataclass(self):
        f = DQFailure("DQ-01","CRITICAL","companies","ticker",1,None,"dup","unique","desc")
        assert f.rule_id == "DQ-01"
        assert "rule_id" in f.__dict__
