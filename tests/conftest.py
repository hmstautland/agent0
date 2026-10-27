import os

# core.ui refuses to start without a session secret - tests use a throwaway one
os.environ.setdefault("SESSION_SECRET", "test-session-secret-" + "x" * 32)

import pytest


@pytest.fixture(autouse=True)
def conversation_db(tmp_path, monkeypatch):
    """Every test gets its own empty database instead of local_storage/agent0.db."""
    import storage.db
    monkeypatch.setattr(storage.db, "DB_PATH", str(tmp_path / "agent0.db"))
    return storage.db.DB_PATH
