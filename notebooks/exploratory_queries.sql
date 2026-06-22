-- ──────────────────────────────────────────────────────────────────────────
-- Nifty-100 Analytics — Exploratory Queries
-- Sprint 1 · Day 07
-- Run against nifty100.db
-- ──────────────────────────────────────────────────────────────────────────

-- ── Q01: Row counts per table ─────────────────────────────────────────────
SELECT 'companies'       AS tbl, COUNT(*) AS rows FROM companies
UNION ALL
SELECT 'profitandloss',          COUNT(*) FROM profitandloss
UNION ALL
SELECT 'balancesheet',           COUNT(*) FROM balancesheet
UNION ALL
SELECT 'cashflow',               COUNT(*) FROM cashflow
UNION ALL
SELECT 'financial_ratios',       COUNT(*) FROM financial_ratios
UNION ALL
SELECT 'stock_prices',           COUNT(*) FROM stock_prices
UNION ALL
SELECT 'analysis',               COUNT(*) FROM analysis
UNION ALL
SELECT 'documents',              COUNT(*) FROM documents
UNION ALL
SELECT 'prosandcons',            COUNT(*) FROM prosandcons
UNION ALL
SELECT 'sectors',                COUNT(*) FROM sectors
ORDER BY rows DESC;

-- ── Q02: Companies per sector ─────────────────────────────────────────────
SELECT
    s.sector_name,
    COUNT(c.company_id) AS company_count
FROM sectors s
LEFT JOIN companies c USING (sector_id)
GROUP BY s.sector_name
ORDER BY company_count DESC;

-- ── Q03: Top 10 companies by average revenue (last 5 years) ──────────────
SELECT
    c.ticker,
    c.company_name,
    ROUND(AVG(pl.revenue), 2)    AS avg_revenue_cr,
    COUNT(pl.fiscal_year)        AS years_of_data
FROM companies c
JOIN profitandloss pl USING (company_id)
WHERE pl.fiscal_year >= (SELECT MAX(fiscal_year) - 4 FROM profitandloss)
GROUP BY c.company_id
HAVING years_of_data >= 3
ORDER BY avg_revenue_cr DESC
LIMIT 10;

-- ── Q04: Year-wise aggregate revenue, EBITDA, net profit ─────────────────
SELECT
    fiscal_year,
    ROUND(SUM(revenue),    2)    AS total_revenue_cr,
    ROUND(SUM(ebitda),     2)    AS total_ebitda_cr,
    ROUND(SUM(net_profit), 2)    AS total_net_profit_cr,
    ROUND(AVG(opm_pct),    2)    AS avg_opm_pct
FROM profitandloss
GROUP BY fiscal_year
ORDER BY fiscal_year;

-- ── Q05: Companies with negative net profit in latest year ────────────────
SELECT
    c.ticker,
    c.company_name,
    pl.fiscal_year,
    ROUND(pl.net_profit, 2) AS net_profit_cr
FROM companies c
JOIN profitandloss pl USING (company_id)
WHERE pl.fiscal_year = (SELECT MAX(fiscal_year) FROM profitandloss)
  AND pl.net_profit < 0
ORDER BY pl.net_profit ASC;

-- ── Q06: Balance-sheet health — debt/equity snapshot ─────────────────────
SELECT
    c.ticker,
    bs.fiscal_year,
    ROUND(bs.total_equity,     2) AS equity_cr,
    ROUND(bs.total_borrowings, 2) AS debt_cr,
    ROUND(
        CASE WHEN bs.total_equity != 0 THEN bs.total_borrowings / bs.total_equity ELSE NULL END,
        2
    )                             AS debt_equity_ratio
FROM companies c
JOIN balancesheet bs USING (company_id)
WHERE bs.fiscal_year = (SELECT MAX(fiscal_year) FROM balancesheet)
ORDER BY debt_equity_ratio DESC NULLS LAST
LIMIT 20;

-- ── Q07: Free cash flow trend for top 5 companies by avg FCF ─────────────
WITH ranked AS (
    SELECT
        company_id,
        ROUND(AVG(free_cash_flow), 2) AS avg_fcf
    FROM cashflow
    GROUP BY company_id
    ORDER BY avg_fcf DESC
    LIMIT 5
)
SELECT
    c.ticker,
    cf.fiscal_year,
    ROUND(cf.free_cash_flow, 2) AS fcf_cr
FROM ranked r
JOIN companies c USING (company_id)
JOIN cashflow   cf USING (company_id)
ORDER BY c.ticker, cf.fiscal_year;

-- ── Q08: Stock price range and volatility (52-week high/low) ─────────────
SELECT
    c.ticker,
    MIN(sp.low)                                    AS low_52w,
    MAX(sp.high)                                   AS high_52w,
    ROUND(MAX(sp.high) - MIN(sp.low), 2)           AS price_range,
    ROUND(
        (MAX(sp.high) - MIN(sp.low)) / MIN(sp.low) * 100,
        2
    )                                              AS range_pct
FROM companies c
JOIN stock_prices sp USING (company_id)
WHERE sp.price_date >= DATE('now', '-365 days')
GROUP BY c.company_id
ORDER BY range_pct DESC
LIMIT 15;

-- ── Q09: Data coverage — companies with all 4 financial tables ───────────
SELECT
    c.ticker,
    c.company_name,
    CASE WHEN EXISTS (SELECT 1 FROM profitandloss  WHERE company_id = c.company_id) THEN 'Y' ELSE 'N' END AS has_pl,
    CASE WHEN EXISTS (SELECT 1 FROM balancesheet   WHERE company_id = c.company_id) THEN 'Y' ELSE 'N' END AS has_bs,
    CASE WHEN EXISTS (SELECT 1 FROM cashflow       WHERE company_id = c.company_id) THEN 'Y' ELSE 'N' END AS has_cf,
    CASE WHEN EXISTS (SELECT 1 FROM stock_prices   WHERE company_id = c.company_id) THEN 'Y' ELSE 'N' END AS has_px
FROM companies c
ORDER BY c.ticker;

-- ── Q10: Analyst rating distribution ─────────────────────────────────────
SELECT
    analyst_rating,
    COUNT(*)                                          AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM analysis
WHERE analyst_rating IS NOT NULL
GROUP BY analyst_rating
ORDER BY count DESC;
