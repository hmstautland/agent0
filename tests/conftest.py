import os

# core.ui refuses to start without a session secret - tests use a throwaway one
os.environ.setdefault("SESSION_SECRET", "test-session-secret-" + "x" * 32)
