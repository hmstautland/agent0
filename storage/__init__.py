"""Persistent storage: the SQLite database and the queries on it.

- db.py: where the database lives, opening it, applying schema.sql
- schema.sql: the tables (and the FTS5 search index)
- conversations.py: saving and finding conversation turns

What the stored data means - which turns go to the model, how answers are
shortened - is not decided here; that is core/conversations.py.
"""
