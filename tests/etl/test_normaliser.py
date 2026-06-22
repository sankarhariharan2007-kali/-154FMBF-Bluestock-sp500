"""
Tests for src/etl/normaliser.py
Sprint 1 · Day 02 — 35+ unit tests covering normalize_year, normalize_ticker,
normalize_column_name, normalize_numeric, clean_string.
"""
from __future__ import annotations

import pytest

from src.etl.normaliser import (
    clean_string,
    normalize_column_name,
    normalize_numeric,
    normalize_ticker,
    normalize_year,
)


# ══════════════════════════════════════════════════════════════
# normalize_year
# ══════════════════════════════════════════════════════════════

class TestNormalizeYear:
    # ── Happy path ──────────────────────────────────────────
    def test_fy_prefix_4digit(self):
        assert normalize_year("FY2023") == 2023

    def test_fy_prefix_lowercase(self):
        assert normalize_year("fy2022") == 2022

    def test_fy_with_space(self):
        assert normalize_year("FY 2020") == 2020

    def test_range_notation_2digit_suffix(self):
        assert normalize_year("2022-23") == 2023

    def test_range_notation_4digit_suffix(self):
        assert normalize_year("2022-2023") == 2023

    def test_range_slash_2digit(self):
        assert normalize_year("2021/22") == 2022

    def test_month_year_mar(self):
        assert normalize_year("Mar-2023") == 2023

    def test_month_year_march(self):
        assert normalize_year("March 2023") == 2023

    def test_month_year_short_year(self):
        assert normalize_year("Mar'23") == 2023

    def test_plain_4digit(self):
        assert normalize_year("2019") == 2019

    def test_integer_input(self):
        assert normalize_year(2023) == 2023

    def test_float_input(self):
        assert normalize_year(2021.0) == 2021

    def test_2digit_year_low(self):
        assert normalize_year("23") == 2023

    def test_2digit_year_high(self):
        assert normalize_year("95") == 1995

    def test_numeric_2digit_int(self):
        assert normalize_year(20) == 2020

    def test_numeric_historical(self):
        assert normalize_year(1999) == 1999

    # ── Edge / error cases ───────────────────────────────────
    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_year(None)

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            normalize_year("not_a_year")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            normalize_year("")


# ══════════════════════════════════════════════════════════════
# normalize_ticker
# ══════════════════════════════════════════════════════════════

class TestNormalizeTicker:
    def test_plain_uppercase(self):
        assert normalize_ticker("RELIANCE") == "RELIANCE"

    def test_lowercase_input(self):
        assert normalize_ticker("reliance") == "RELIANCE"

    def test_strip_ns_suffix(self):
        assert normalize_ticker("TCS.NS") == "TCS"

    def test_strip_bo_suffix(self):
        assert normalize_ticker("INFY.BO") == "INFY"

    def test_strip_nse_suffix(self):
        assert normalize_ticker("HDFC.NSE") == "HDFC"

    def test_strip_bse_suffix(self):
        assert normalize_ticker("WIPRO.BSE") == "WIPRO"

    def test_leading_trailing_spaces(self):
        assert normalize_ticker("  TCS  ") == "TCS"

    def test_internal_spaces_removed(self):
        assert normalize_ticker("HDFC BANK") == "HDFCBANK"

    def test_mixed_case_with_suffix(self):
        assert normalize_ticker("reliance.ns") == "RELIANCE"

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker(None)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker("")

    def test_spaces_only_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker("   ")

    def test_ampersand_preserved(self):
        # Some tickers legitimately have & (e.g. M&M)
        assert normalize_ticker("M&M") == "M&M"


# ══════════════════════════════════════════════════════════════
# normalize_column_name
# ══════════════════════════════════════════════════════════════

class TestNormalizeColumnName:
    def test_basic(self):
        assert normalize_column_name("Revenue") == "revenue"

    def test_percent_replaced(self):
        assert normalize_column_name("OPM %") == "opm_pct"

    def test_parenthetical_stripped(self):
        result = normalize_column_name("Net Profit (₹ Cr)")
        assert "(" not in result
        assert "₹" not in result
        assert "net_profit" in result

    def test_slash_replaced(self):
        result = normalize_column_name("P/E Ratio")
        assert "ratio" in result
        assert "/" not in result

    def test_no_double_underscores(self):
        result = normalize_column_name("Net  Profit  %")
        assert "__" not in result

    def test_strip_trailing_underscore(self):
        result = normalize_column_name("Revenue ")
        assert not result.startswith("_")
        assert not result.endswith("_")


# ══════════════════════════════════════════════════════════════
# normalize_numeric
# ══════════════════════════════════════════════════════════════

class TestNormalizeNumeric:
    def test_plain_float(self):
        assert normalize_numeric(1234.56) == 1234.56

    def test_plain_int(self):
        assert normalize_numeric(100) == 100.0

    def test_comma_separated(self):
        assert normalize_numeric("1,23,456.78") == pytest.approx(123456.78)

    def test_currency_prefix(self):
        assert normalize_numeric("₹1,234") == pytest.approx(1234.0)

    def test_dash_returns_none(self):
        assert normalize_numeric("-") is None

    def test_none_returns_none(self):
        assert normalize_numeric(None) is None

    def test_empty_returns_none(self):
        assert normalize_numeric("") is None

    def test_na_returns_none(self):
        assert normalize_numeric("N/A") is None

    def test_unit_multiplier_applied(self):
        assert normalize_numeric(100, unit_multiplier=10.0) == pytest.approx(1000.0)

    def test_negative_value(self):
        assert normalize_numeric("-500.5") == pytest.approx(-500.5)


# ══════════════════════════════════════════════════════════════
# clean_string
# ══════════════════════════════════════════════════════════════

class TestCleanString:
    def test_basic_strip(self):
        assert clean_string("  hello  ") == "hello"

    def test_internal_spaces_collapsed(self):
        assert clean_string("hello   world") == "hello world"

    def test_none_returns_none(self):
        assert clean_string(None) is None

    def test_empty_returns_none(self):
        assert clean_string("") is None

    def test_nan_returns_none(self):
        assert clean_string("nan") is None

    def test_na_returns_none(self):
        assert clean_string("N/A") is None

    def test_dash_returns_none(self):
        assert clean_string("-") is None

    def test_max_len_truncates(self):
        result = clean_string("abcdefgh", max_len=5)
        assert result is not None
        assert len(result) <= 5

    def test_numeric_converted_to_string(self):
        # clean_string converts non-strings
        result = clean_string(12345)
        assert result == "12345"
