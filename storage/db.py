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
_SAFE_DB_ROOT = Path("local_storage").resolve()
_DEFAULT_DB_PATH = _SAFE_DB_ROOT / "agent0.db"

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
# Bump when schema.sql changes - databases below it get schema.sql applied again
SCHEMA_VERSION = 2


def _validated_db_path():
    """Return a normalized DB path constrained to the local_storage directory."""
    candidate = Path(DB_PATH).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(_SAFE_DB_ROOT)
    except ValueError as exc:
        raise ValueError(
            f"AGENT0_DB must stay within '{_SAFE_DB_ROOT}', got '{DB_PATH}'"
        ) from exc
    return resolved


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
    db_path = _validated_db_path()
    os.makedirs(db_path.parent, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        _migrate(conn)
        with conn:
            yield conn
    finally:
        conn.close()
