"""On/off flags for integrations (the Config page). Off unless switched on."""
from storage.db import connect, now


def is_enabled(key):
    with connect() as conn:
        row = conn.execute("SELECT enabled FROM integration_flags WHERE key = ?", (key,)).fetchone()
    return bool(row and row["enabled"])


def set_enabled(key, enabled):
    with connect() as conn:
        conn.execute(
            "INSERT INTO integration_flags (key, enabled, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at",
            (key, 1 if enabled else 0, now()),
        )
