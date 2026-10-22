"""The SQLite database: where it lives and opening it with the schema in place.

One connection per call (`with connect() as conn:`) keeps it safe to use from
the worker threads the streaming responses run in.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = os.getenv("AGENT0_DB", "local_storage/agent0.db")

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
# Bump when schema.sql changes - databases below it get schema.sql applied again
SCHEMA_VERSION = 2


def now():
    """Timestamp format used in every table (ISO 8601, local time, seconds)."""
    return datetime.now().isoformat(timespec="seconds")


def _migrate(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    # Version 1 had no search index: index the turns already stored
    conn.execute("INSERT INTO turns_fts(turns_fts) VALUES ('rebuild')")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


@contextmanager
def connect():
    """An open connection with the schema applied; commits on success, rolls back on error."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        _migrate(conn)
        with conn:
            yield conn
    finally:
        conn.close()
