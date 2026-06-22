"""Tests for src/utils/db.py"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.utils.db import db_session, fk_check, get_connection, init_schema, table_counts


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "test.db"
    schema = Path("db/schema.sql")
    if schema.exists():
        conn = sqlite3.connect(str(db))
        conn.executescript(schema.read_text())
        conn.commit()
        conn.close()
    return db


def test_get_connection_returns_connection(tmp_db):
    conn = get_connection(tmp_db)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_fk_enabled(tmp_db):
    with db_session(tmp_db, commit=False) as conn:
        result = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert result == 1


def test_fk_check_clean(tmp_db):
    violations = fk_check(tmp_db)
    assert violations == []


def test_table_counts_returns_dict(tmp_db):
    counts = table_counts(tmp_db)
    assert isinstance(counts, dict)
    assert "companies" in counts
    assert counts["companies"] == 0


def test_db_session_rollback_on_error(tmp_db):
    with pytest.raises(ValueError):
        with db_session(tmp_db) as conn:
            conn.execute("INSERT INTO sectors (sector_name) VALUES (?);", ("TestSector",))
            raise ValueError("Forced rollback")
    # After rollback, count should still be 0
    counts = table_counts(tmp_db)
    assert counts.get("sectors", 0) == 0
