# Nifty-100 Analytics — Sprint 1: Data Ingestion & ETL

> **Epic 01 · 34 SP** — Full ETL pipeline loading 12 source Excel files into a validated 10-table SQLite database (`nifty100.db`).

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/sankarhariharan2007-kali/-154FMBF-Bluestock-sp500.git
cd -154FMBF-Bluestock-sp500

# 2. Setup environment (creates venv, installs 20 libs, creates dirs, copies .env)
make setup

# 3. Place source Excel files in data/raw/  (see Source Files section)

# 4. Initialise DB schema
make db-init

# 5. Load all data
make db-load

# 6. Run DQ rules
make validate

# 7. Run tests
make test

# 8. Sprint exit-criteria check
make sprint-check
```

---

## Project Structure

```
.
├── Makefile                     # All pipeline targets
├── requirements.txt             # 20 Python dependencies
├── .env.example                 # Environment template
├── setup.py
│
├── db/
│   └── schema.sql               # 10-table SQLite schema + indexes
│
├── src/
│   ├── etl/
│   │   ├── loader.py            # ETL loader — 10 table-specific loaders
│   │   ├── validator.py         # 16 DQ rules → validation_failures.csv
│   │   └── normaliser.py        # normalize_year, normalize_ticker, etc.
│   └── utils/
│       ├── config.py            # Typed config from .env
│       ├── db.py                # SQLite connection helpers
│       └── logger.py            # Loguru console + file logger
│
├── tests/
│   └── etl/
│       ├── test_normaliser.py   # 35+ unit tests
│       └── test_db.py           # DB utility tests
│
├── notebooks/
│   └── exploratory_queries.sql  # 10 analytical SQL queries
│
├── output/                      # Generated (gitignored)
│   ├── load_audit.csv
│   └── validation_failures.csv
│
├── data/
│   ├── raw/                     # Source Excel files (gitignored)
│   └── processed/
│
└── logs/                        # Runtime logs (gitignored)
```

---

## Source Files (place in `data/raw/`)

### Core (7)
| File | Target Table |
|------|-------------|
| `companies.xlsx` | `companies` |
| `sectors.xlsx` | `sectors` |
| `profit_and_loss.xlsx` | `profitandloss` |
| `balance_sheet.xlsx` | `balancesheet` |
| `cash_flow.xlsx` | `cashflow` |
| `stock_prices.xlsx` | `stock_prices` |
| `financial_ratios.xlsx` | `financial_ratios` |

### Supplementary (5)
| File | Target Table |
|------|-------------|
| `analysis.xlsx` | `analysis` |
| `documents.xlsx` | `documents` |
| `prosandcons.xlsx` | `prosandcons` |
| `peer_groups.xlsx` | *(future sprint)* |
| `market_data.xlsx` | *(future sprint)* |

---

## Database Schema (10 Tables)

```
sectors          ← master
companies        → sectors
profitandloss    → companies  (UK: company_id, fiscal_year)
balancesheet     → companies  (UK: company_id, fiscal_year)
cashflow         → companies  (UK: company_id, fiscal_year)
financial_ratios → companies  (UK: company_id, fiscal_year)
stock_prices     → companies  (UK: company_id, price_date)
analysis         → companies
documents        → companies
prosandcons      → companies
```

---

## 16 Data Quality Rules

| Rule | Severity | Description |
|------|----------|-------------|
| DQ-01 | CRITICAL | PK uniqueness — `companies.ticker` |
| DQ-02 | CRITICAL | Composite PK `(company_id, fiscal_year)` in P&L / BS / CF / Ratios |
| DQ-03 | CRITICAL | FK integrity (`PRAGMA foreign_key_check`) |
| DQ-04 | WARNING  | Balance-sheet balance < 1% tolerance |
| DQ-05 | WARNING  | OPM cross-check (reported vs computed) |
| DQ-06 | WARNING  | Revenue > 0 |
| DQ-07 | CRITICAL | `fiscal_year` in [2000, 2030] |
| DQ-08 | CRITICAL | No NULL tickers in companies |
| DQ-09 | WARNING  | Duplicate company names |
| DQ-10 | WARNING  | Stock close price > 0 |
| DQ-11 | WARNING  | EPS sign consistent with net_profit |
| DQ-12 | WARNING  | Companies with < 3 years P&L |
| DQ-13 | WARNING  | Negative equity |
| DQ-14 | WARNING  | Interest coverage (EBIT < 0 and interest > 0) |
| DQ-15 | WARNING  | Companies with P&L but no CF data |
| DQ-16 | WARNING  | Companies with no stock price data |

---

## Sprint 1 Exit Criteria

| Criterion | Target |
|-----------|--------|
| `SELECT COUNT(*) FROM companies` | 92 |
| `PRAGMA foreign_key_check` | 0 rows |
| `load_audit.csv` CRITICAL rejections | 0 |
| Unit tests passing | 35+ |
| Manual review (5 companies) | Correct |

Run `make sprint-check` to verify all criteria.

---

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Full environment setup |
| `make db-init` | Create SQLite schema |
| `make db-load` | Load all source files |
| `make validate` | Run 16 DQ rules |
| `make test` | Run pytest suite |
| `make test-cov` | Tests with coverage report |
| `make sprint-check` | Verify all exit criteria |
| `make demo` | Print table row counts |
| `make lint` | flake8 |
| `make format` | black + isort |
| `make clean-all` | Remove venv, DB, outputs |

---

## Dependencies (20 libraries)

`pandas` · `numpy` · `openpyxl` · `xlrd` · `sqlalchemy` · `python-dotenv` · `pytest` · `pytest-cov` · `pytest-mock` · `black` · `isort` · `flake8` · `mypy` · `loguru` · `tqdm` · `tabulate` · `pydantic` · `colorama` · `rich` · `pyarrow`
