"""
db/connection.py
================
Manages SQLite database connections and automatic schema initialization.
Enforces foreign keys, row factory mapping, parent directory creation,
and transactional safety.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from feedback_analyzer.config import get_config

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql on the connection to ensure tables and indexes exist."""
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    Open and configure a SQLite connection.
    Automatically creates the parent directory and initializes schema on first connection.

    Args:
        db_path: Path to the SQLite database file, or ':memory:'.
                 If None, reads db_path from application config.

    Returns:
        Configured sqlite3.Connection instance with foreign keys enabled and Row factory set.
    """
    if db_path is None:
        db_path = get_config().db_path

    # If file-based database, ensure directory exists
    if str(db_path) != ":memory:":
        p = Path(db_path)
        p.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    # Ensure schema is applied
    init_db(conn)
    return conn


@contextmanager
def connection_scope(
    db_path: str | Path | None = None,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager providing a transactional SQLite connection.
    Automatically commits on normal completion, rolls back on exception,
    and closes the connection upon exit.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
