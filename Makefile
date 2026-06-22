# ──────────────────────────────────────────────────────────────
# Nifty-100 Analytics — Makefile
# ──────────────────────────────────────────────────────────────
SHELL        := /bin/bash
PYTHON       := python
VENV         := venv
PIP          := $(VENV)/bin/pip
PYTEST       := $(VENV)/bin/pytest
BLACK        := $(VENV)/bin/black
ISORT        := $(VENV)/bin/isort
FLAKE8       := $(VENV)/bin/flake8
MYPY         := $(VENV)/bin/mypy

DB           := nifty100.db
OUTPUT_DIR   := output
LOG_DIR      := logs

.PHONY: all setup venv install dirs env \
        lint format typecheck \
        load validate \
        test test-cov \
        db-init db-load db-check \
        clean clean-db clean-outputs clean-all \
        demo sprint-check

# ── Default ──────────────────────────────────────────────────
all: setup

# ── Environment ──────────────────────────────────────────────
setup: venv install dirs env
	@echo "✅  Environment ready. Run 'make db-init' to create the schema."

venv:
	@echo "→ Creating virtual environment…"
	$(PYTHON) -m venv $(VENV)

install: venv
	@echo "→ Installing dependencies…"
	$(PIP) install --upgrade pip wheel
	$(PIP) install -r requirements.txt

dirs:
	@echo "→ Creating project directories…"
	mkdir -p src/etl src/utils db output/reports notebooks tests/etl \
	         data/raw data/processed logs

env:
	@if [ ! -f .env ]; then \
	    cp .env.example .env; \
	    echo "→ .env created from .env.example — review before running."; \
	else \
	    echo "→ .env already exists, skipping."; \
	fi

# ── Code Quality ─────────────────────────────────────────────
lint:
	$(FLAKE8) src/ tests/ --max-line-length=120

format:
	$(BLACK) src/ tests/ --line-length=120
	$(ISORT) src/ tests/

typecheck:
	$(MYPY) src/ --ignore-missing-imports

# ── Database ─────────────────────────────────────────────────
db-init:
	@echo "→ Initialising SQLite schema…"
	$(VENV)/bin/python -c "\
	import sqlite3, os; \
	conn = sqlite3.connect('$(DB)'); \
	conn.execute('PRAGMA foreign_keys = ON'); \
	with open('db/schema.sql') as f: conn.executescript(f.read()); \
	conn.commit(); conn.close(); \
	print('✅  $(DB) schema created.')"

db-load:
	@echo "→ Loading all source files…"
	$(VENV)/bin/python -m src.etl.loader --all

db-check:
	@echo "→ Running FK integrity check…"
	$(VENV)/bin/python -c "\
	import sqlite3; \
	conn = sqlite3.connect('$(DB)'); \
	conn.execute('PRAGMA foreign_keys = ON'); \
	rows = conn.execute('PRAGMA foreign_key_check').fetchall(); \
	print(f'FK violations: {len(rows)}'); \
	[print(r) for r in rows]; \
	conn.close()"

# ── ETL Pipeline ─────────────────────────────────────────────
load: db-init db-load db-check
	@echo "✅  Full load complete."

validate:
	@echo "→ Running 16 DQ rules…"
	$(VENV)/bin/python -m src.etl.validator

# ── Tests ────────────────────────────────────────────────────
test:
	$(PYTEST) tests/ -v

test-cov:
	$(PYTEST) tests/ --cov=src --cov-report=html --cov-report=term-missing -v

# ── Sprint Checks (Exit Criteria) ────────────────────────────
sprint-check:
	@echo "═══════════════════════════════════════"
	@echo " Sprint 1 — Exit Criteria Check"
	@echo "═══════════════════════════════════════"
	$(VENV)/bin/python -c "\
	import sqlite3; \
	conn = sqlite3.connect('$(DB)'); \
	conn.execute('PRAGMA foreign_keys = ON'); \
	n = conn.execute('SELECT COUNT(*) FROM companies').fetchone()[0]; \
	fk = conn.execute('PRAGMA foreign_key_check').fetchall(); \
	print(f'companies count : {n}  (expected 92)'); \
	print(f'FK violations   : {len(fk)}  (expected 0)'); \
	conn.close()"
	@echo "→ Checking load_audit.csv for CRITICAL rejections…"
	@python -c "\
	import csv, sys; \
	try: \
	    rows = list(csv.DictReader(open('output/load_audit.csv'))); \
	    crit = [r for r in rows if r.get('status','').upper() == 'CRITICAL']; \
	    print(f'CRITICAL rejections : {len(crit)}  (expected 0)'); \
	except FileNotFoundError: \
	    print('output/load_audit.csv not found — run make load first')"
	@echo "→ Test suite…"
	$(PYTEST) tests/ -q

# ── Demo ─────────────────────────────────────────────────────
demo:
	$(VENV)/bin/python -c "\
	import sqlite3; \
	conn = sqlite3.connect('$(DB)'); \
	tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")]; \
	print('Tables in $(DB):'); \
	for t in tables: \
	    n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]; \
	    print(f'  {t:<25} {n:>6} rows'); \
	conn.close()"

# ── Clean ────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache htmlcov .coverage

clean-db:
	rm -f $(DB) $(DB)-shm $(DB)-wal

clean-outputs:
	rm -f output/*.csv output/reports/*

clean-all: clean clean-db clean-outputs
	rm -rf $(VENV)
	@echo "✅  Project cleaned."
