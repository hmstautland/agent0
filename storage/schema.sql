-- agent0's database (storage/db.py applies this when the database's
-- user_version is below SCHEMA_VERSION). Every statement must be safe to run
-- again on an existing database.

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,          -- the first question, shortened
    created_at TEXT NOT NULL,     -- ISO 8601, local time
    updated_at TEXT NOT NULL
);

-- One finished request: the question, the final answer, and one line per
-- tool call that ran ("edit_file static/styles.css").
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    created_at TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    actions TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS turns_by_conversation ON turns(conversation_id, id);

-- Full-text index over turns (for search_history). External content: the text
-- lives only in turns, the triggers keep the index in step with it.
-- unicode61 splits on punctuation, so "styles.css" is indexed as "styles" "css".
CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
    question, answer, actions,
    content='turns', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS turns_fts_insert AFTER INSERT ON turns BEGIN
    INSERT INTO turns_fts(rowid, question, answer, actions)
    VALUES (new.id, new.question, new.answer, new.actions);
END;

CREATE TRIGGER IF NOT EXISTS turns_fts_delete AFTER DELETE ON turns BEGIN
    INSERT INTO turns_fts(turns_fts, rowid, question, answer, actions)
    VALUES ('delete', old.id, old.question, old.answer, old.actions);
END;

CREATE TRIGGER IF NOT EXISTS turns_fts_update AFTER UPDATE ON turns BEGIN
    INSERT INTO turns_fts(turns_fts, rowid, question, answer, actions)
    VALUES ('delete', old.id, old.question, old.answer, old.actions);
    INSERT INTO turns_fts(rowid, question, answer, actions)
    VALUES (new.id, new.question, new.answer, new.actions);
END;
