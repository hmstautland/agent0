import sqlite3
from datetime import datetime, timedelta

import pytest

import storage.db as db
from storage.conversations import fts_query, recent_turns, save_turn, search_turns


def questions(rows):
    return [row["question"] for row in rows]


def test_turns_are_kept_per_conversation_oldest_first(conversation_db):
    save_turn("a", "first", "1")
    save_turn("b", "other", "x")
    save_turn("a", "second", "2", ["edit_file x.py", "verify_app"])

    rows = recent_turns("a", 10)

    assert questions(rows) == ["first", "second"]
    assert rows[1]["actions"] == "edit_file x.py\nverify_app"
    assert questions(recent_turns("a", 1)) == ["second"]


def test_search_matches_words_in_question_answer_or_actions_across_conversations(conversation_db):
    save_turn("a", "make the UI support light mode", "Done.", ["edit_file static/styles.css"])
    save_turn("b", "weather tomorrow?", "Sunny in Oslo.")

    assert questions(search_turns("styles.css")) == ["make the UI support light mode"]
    assert questions(search_turns("oslo")) == ["weather tomorrow?"]
    assert search_turns("light oslo") == []  # every word must match


def test_search_matches_word_starts_and_ignores_accents(conversation_db):
    save_turn("a", "add lightmode to the café page", "ok")

    assert questions(search_turns("light")) == ["add lightmode to the café page"]
    assert questions(search_turns("cafe")) == ["add lightmode to the café page"]


def test_search_ranks_the_best_match_first(conversation_db):
    save_turn("a", "calendar", "mentions grey once")
    save_turn("a", "make the background grey", "grey grey, a light grey background")
    save_turn("a", "unrelated", "nothing")

    assert questions(search_turns("grey")) == ["make the background grey", "calendar"]


def test_search_without_a_query_is_newest_first_and_can_be_limited_to_recent(conversation_db, monkeypatch):
    monkeypatch.setattr("storage.conversations.now", lambda: (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds"))
    save_turn("a", "long ago", "ok")
    monkeypatch.setattr("storage.conversations.now", db.now)
    save_turn("a", "today", "ok")

    assert questions(search_turns()) == ["today", "long ago"]
    since = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    assert questions(search_turns(since=since)) == ["today"]
    assert questions(search_turns(limit=1)) == ["today"]


@pytest.mark.parametrize("text", ['"', "AND", "NEAR(a b)", "col:value", "a* OR -b", "(((", "^x"])
def test_fts_syntax_in_the_query_is_matched_literally_not_run(conversation_db, text):
    save_turn("a", "plain question", "plain answer")
    search_turns(text)  # must not raise


def test_fts_query_quotes_each_word_and_gives_none_without_words():
    assert fts_query('light "mode') == '"light"* "mode"*'
    assert fts_query("?!") is None
    assert fts_query(None) is None


def test_an_old_database_without_the_search_index_is_upgraded_and_indexed(conversation_db):
    conn = sqlite3.connect(db.DB_PATH)
    conn.executescript("""
        CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE turns (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, created_at TEXT NOT NULL,
                            question TEXT NOT NULL, answer TEXT NOT NULL, actions TEXT NOT NULL DEFAULT '');
        INSERT INTO conversations VALUES ('a', 'old', '2026-10-18T10:00:00', '2026-10-18T10:00:00');
        INSERT INTO turns (conversation_id, created_at, question, answer) VALUES ('a', '2026-10-18T10:00:00', 'stored before search existed', 'ok');
    """)
    conn.close()

    assert questions(search_turns("search existed")) == ["stored before search existed"]
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_a_failed_write_is_rolled_back(conversation_db):
    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("INSERT INTO conversations VALUES ('a', 't', 'x', 'x')")
            conn.execute("INSERT INTO conversations VALUES ('a', 't', 'x', 'x')")

    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM conversations").fetchone()[0] == 0
