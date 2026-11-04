"""Conversation memory: what was asked and answered earlier.

Each login session (or CLI process) talks in one conversation until the user
starts a new one. Every finished request is stored as a turn - the question,
the final answer, and a short list of what the tools did ("edit_file
static/styles.css") - so a follow-up like "make that background grey" can be
understood. Only those summaries are replayed to the model, never the tool
results themselves: they are small, and the files can be read again.

All conversations stay stored (storage/, SQLite), so the agent can look
earlier ones up with the search_history tool.
"""
import secrets
from datetime import datetime, timedelta

from core.logger import log_event
from storage import conversations as store

# How much earlier conversation each request is sent: the newest turns that
# fit, oldest dropped first. Small enough for the light model's 8k window.
HISTORY_TURNS = 6
HISTORY_CHARS = 6000
# One long answer (a file listing, a pasted article) can't take the whole budget
TURN_ANSWER_CHARS = 1500

SEARCH_ANSWER_CHARS = 400


def new_conversation():
    """A fresh conversation id. Nothing is stored until its first turn."""
    return secrets.token_urlsafe(12)


def _shorten(text, limit):
    return text if len(text) <= limit else text[:limit] + " [...]"


def _assistant_text(turn):
    answer = _shorten(turn["answer"], TURN_ANSWER_CHARS)
    if turn["actions"]:
        return f"[Tools used: {'; '.join(turn['actions'].splitlines())}]\n{answer}"
    return answer


def history_messages(conversation_id, limit=HISTORY_TURNS, budget=HISTORY_CHARS):
    """Earlier turns as user/assistant chat messages, to put before the new question."""
    if not conversation_id:
        return []

    messages = []
    used = 0
    for turn in reversed(store.recent_turns(conversation_id, limit)):
        pair = [
            {"role": "user", "content": turn["question"]},
            {"role": "assistant", "content": _assistant_text(turn)},
        ]
        size = sum(len(m["content"]) for m in pair)
        if used + size > budget:
            break
        messages[:0] = pair
        used += size
    return messages


def search_history(query=None, days=None, limit=10):
    """Tool: search earlier conversations (all sessions).

    Full-text search over the questions, answers and tools used, best match
    first; without a query, the most recent turns. `days` limits it to the
    last N days.
    """
    since = (datetime.now() - timedelta(days=int(days))).isoformat(timespec="seconds") if days else None
    rows = store.search_turns(query, since=since, limit=max(1, min(int(limit), 50)))

    if not rows:
        return "No earlier conversations matched." if query or days else "No earlier conversations yet."

    return [
        {
            "when": row["created_at"].replace("T", " "),
            "conversation": row["title"],
            "question": row["question"],
            "answer": _shorten(row["answer"], SEARCH_ANSWER_CHARS),
            "tools_used": row["actions"].splitlines(),
        }
        for row in rows
    ]


def record(events, conversation_id, question, actions=()):
    """Pass events through, storing the turn when the request finishes.

    `actions` is read when the final event arrives, so a list the run is
    still filling in (AgentRun.actions) can be passed as is. A run parked for
    approval is not recorded here - its resume is.
    """
    for event in events:
        kind = event.get("event")
        if conversation_id and kind in ("final_response", "error"):
            try:
                store.save_turn(conversation_id, question, _turn_answer(event), list(actions))
            except Exception as e:
                # Memory is a convenience - a database problem must not eat the answer
                log_event({"type": "conversation_save_failed", "error": repr(e)})
        yield event


def _turn_answer(event):
    if event.get("event") == "error":
        return f"(Failed: {event.get('message')})"
    answer = event.get("response") or ""
    shown = event.get("show_calendar")
    if shown and not answer:
        answer = f"(Opened the calendar at {shown['year']}-{shown['month']:02d})"
    return answer
