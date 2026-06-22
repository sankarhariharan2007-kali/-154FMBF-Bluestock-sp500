"""
Database connection helpers for nifty100.db.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.utils.config import cfg
from src.utils.logger import logger


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with FK enforcement and WAL mode."""
    path = Path(db_path) if db_path else cfg.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(f"PRAGMA journal_mode = {cfg.SQLITE_JOURNAL_MODE};")
    logger.debug(f"Opened DB connection → {path}")
    return conn


@contextmanager
def db_session(
    db_path: Path | str | None = None,
    commit: bool = True,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager: open connection, yield, commit (or rollback), close."""
    conn = get_connection(db_path)
    try:
        yield conn
        if commit:
            conn.commit()
            logger.debug("Transaction committed.")
    except Exception:
        conn.rollback()
        logger.error("Transaction rolled back due to exception.")
        raise
    finally:
        conn.close()
        logger.debug("DB connection closed.")


def init_schema(db_path: Path | str | None = None, schema_path: Path | str | None = None) -> None:
    """Execute schema.sql against the target database."""
    schema = Path(schema_path) if schema_path else Path("db/schema.sql")
    if not schema.exists():
        raise FileNotFoundError(f"Schema file not found: {schema}")

    with db_session(db_path) as conn:
        conn.executescript(schema.read_text())
    logger.info(f"Schema applied from {schema}")


def fk_check(db_path: Path | str | None = None) -> list[sqlite3.Row]:
    """Run PRAGMA foreign_key_check and return violations."""
    with db_session(db_path, commit=False) as conn:
        violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if violations:
        logger.warning(f"FK violations found: {len(violations)}")
    else:
        logger.info("FK check passed — 0 violations.")
    return violations


def table_counts(db_path: Path | str | None = None) -> dict[str, int]:
    """Return row counts for all user tables."""
    with db_session(db_path, commit=False) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
        ]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0] for t in tables}
