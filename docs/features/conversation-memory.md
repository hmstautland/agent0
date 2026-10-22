# Conversation memory

The agent remembers the current conversation, so follow-ups like "make that background grey" work. It can also look up earlier conversations.

## Using it

- Just keep chatting. Each login session (CLI: each process) is one conversation.
- Start a fresh one with the **+** button (web) or `/new` (CLI). Logging out also starts a new one.
- Ask about earlier sessions ("what did we change yesterday?"). The model uses the `search_history` tool for that.

## How it works

Every finished request is stored as a turn: the question, the final answer, and a one-line summary of each tool call that ran (e.g. `edit_file static/styles.css`). The newest turns are sent with each new question as plain user/assistant text, with a `[Tools used: ...]` line. Tool results themselves are never replayed, because they're large and the files can be read again.

Everything is stored in SQLite (`local_storage/agent0.db`, via `storage/`) with a full-text index, so `search_history` finds the best matches across all sessions.

Code: `core/conversations.py`, `storage/conversations.py`, `storage/schema.sql`.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `HISTORY_TURNS` (`core/conversations.py`) | `6` | Most earlier turns sent with a question |
| `HISTORY_CHARS` (`core/conversations.py`) | `6000` | Character budget for those turns (oldest dropped first) |
| `AGENT0_DB` (env) | `local_storage/agent0.db` | Database location |

## Limits

- A stopped request isn't stored.
- Long answers are cut to 1500 characters when they're replayed as history.
