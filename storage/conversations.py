"""Saving and finding conversation turns (tables in schema.sql)."""
import re

from storage.db import connect, now


def save_turn(conversation_id, question, answer, actions=()):
    """Store one finished request, creating the conversation on its first turn."""
    timestamp = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
            (conversation_id, question[:80], timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO turns (conversation_id, created_at, question, answer, actions) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, timestamp, question, answer or "", "\n".join(actions)),
        )


def recent_turns(conversation_id, limit):
    """The newest `limit` turns of one conversation, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM turns WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def fts_query(text):
    """Turn free text into a safe FTS5 query: every word must appear, as a word or a word's start.

    Each word is quoted, so FTS5 syntax in the text (AND, NEAR, "*", ":")
    is matched literally instead of raising. "light mode" -> "light"* "mode"*
    Returns None if the text has no words.
    """
    words = re.findall(r"\w+", text or "")
    return " ".join(f'"{word}"*' for word in words) or None


def search_turns(query=None, since=None, limit=10):
    """Turns from every conversation, with their conversation's title.

    With a query: full-text matches in the question, answer or actions, best
    match first. Without one: newest first. `since` is an ISO timestamp.
    """
    match = fts_query(query)
    sql = "SELECT t.*, c.title FROM turns t JOIN conversations c ON c.id = t.conversation_id"
    where, params = [], []
    if match:
        sql += " JOIN turns_fts f ON f.rowid = t.id"
        where.append("turns_fts MATCH ?")
        params.append(match)
    if since:
        where.append("t.created_at >= ?")
        params.append(since)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + ("bm25(turns_fts), t.id DESC" if match else "t.id DESC") + " LIMIT ?"
    params.append(limit)

    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
