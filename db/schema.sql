-- ──────────────────────────────────────────────────────────────────────────
-- Nifty-100 Analytics — SQLite Schema
-- Sprint 1 · Day 04
-- 10 tables: companies, sectors, profitandloss, balancesheet, cashflow,
--            analysis, documents, prosandcons, stock_prices, financial_ratios
-- ──────────────────────────────────────────────────────────────────────────

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ── 1. sectors ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sectors (
    sector_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    sector_name TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── 2. companies ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    company_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL UNIQUE,           -- e.g. RELIANCE
    company_name    TEXT    NOT NULL,
    sector_id       INTEGER REFERENCES sectors(sector_id) ON DELETE SET NULL,
    market_cap_cr   REAL,
    nse_listed      INTEGER NOT NULL DEFAULT 1,        -- boolean
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_companies_ticker   ON companies(ticker);
CREATE INDEX IF NOT EXISTS idx_companies_sector   ON companies(sector_id);

-- ── 3. profitandloss ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS profitandloss (
    pl_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year         INTEGER NOT NULL,              -- e.g. 2023 = FY2022-23
    revenue             REAL,
    other_income        REAL,
    total_income        REAL,
    expenses            REAL,
    ebitda              REAL,
    depreciation        REAL,
    ebit                REAL,
    interest            REAL,
    pbt                 REAL,
    tax                 REAL,
    net_profit          REAL,
    eps                 REAL,
    opm_pct             REAL,                          -- Operating Profit Margin %
    npm_pct             REAL,                          -- Net Profit Margin %
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_pl_company_year ON profitandloss(company_id, fiscal_year);

-- ── 4. balancesheet ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balancesheet (
    bs_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year         INTEGER NOT NULL,
    share_capital       REAL,
    reserves            REAL,
    total_equity        REAL,
    long_term_debt      REAL,
    short_term_debt     REAL,
    total_borrowings    REAL,
    total_liabilities   REAL,
    fixed_assets        REAL,
    cwip                REAL,                          -- Capital Work In Progress
    investments         REAL,
    current_assets      REAL,
    current_liabilities REAL,
    total_assets        REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_bs_company_year ON balancesheet(company_id, fiscal_year);

-- ── 5. cashflow ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cashflow (
    cf_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year         INTEGER NOT NULL,
    cfo                 REAL,                          -- Cash from Operations
    cfi                 REAL,                          -- Cash from Investing
    cff                 REAL,                          -- Cash from Financing
    net_cash_flow       REAL,
    capex               REAL,
    free_cash_flow      REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_cf_company_year ON cashflow(company_id, fiscal_year);

-- ── 6. financial_ratios ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financial_ratios (
    ratio_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year         INTEGER NOT NULL,
    pe_ratio            REAL,
    pb_ratio            REAL,
    ev_ebitda           REAL,
    roe_pct             REAL,
    roce_pct            REAL,
    debt_equity         REAL,
    current_ratio       REAL,
    quick_ratio         REAL,
    dividend_yield_pct  REAL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_ratios_company_year ON financial_ratios(company_id, fiscal_year);

-- ── 7. stock_prices ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stock_prices (
    price_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    price_date      TEXT    NOT NULL,                  -- ISO-8601: YYYY-MM-DD
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume          INTEGER,
    adj_close       REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, price_date)
);

CREATE INDEX IF NOT EXISTS idx_prices_company_date ON stock_prices(company_id, price_date);
CREATE INDEX IF NOT EXISTS idx_prices_date          ON stock_prices(price_date);

-- ── 8. analysis ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analysis (
    analysis_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    fiscal_year     INTEGER NOT NULL,
    analyst_rating  TEXT,                              -- BUY / HOLD / SELL
    target_price    REAL,
    upside_pct      REAL,
    risk_level      TEXT,                              -- LOW / MEDIUM / HIGH
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, fiscal_year)
);

-- ── 9. documents ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    doc_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    doc_type        TEXT    NOT NULL,                  -- Annual Report / Concall / etc.
    fiscal_year     INTEGER,
    title           TEXT,
    url             TEXT,
    source_file     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_docs_company ON documents(company_id);

-- ── 10. prosandcons ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prosandcons (
    poc_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    type            TEXT    NOT NULL CHECK (type IN ('PRO', 'CON')),
    description     TEXT    NOT NULL,
    fiscal_year     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_poc_company ON prosandcons(company_id);

-- ── 11. peer_groups ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS peer_groups (
    peer_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    peer_company_id INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    sector          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, peer_company_id)
);

CREATE INDEX IF NOT EXISTS idx_pg_company ON peer_groups(company_id);

-- ── Audit / Meta ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS load_audit_log (
    audit_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name      TEXT    NOT NULL,
    source_file     TEXT,
    rows_attempted  INTEGER,
    rows_inserted   INTEGER,
    rows_rejected   INTEGER,
    status          TEXT,                              -- OK / WARNING / CRITICAL
    run_at          TEXT NOT NULL DEFAULT (datetime('now')),
    notes           TEXT
);
