"""Agent runs paused on a tool call that needs the user's approval.

When the tool loop reaches a call that needs approval, the whole run (chat
history, queued tool calls, the call itself) is parked here under a fresh
random id, and the approval card only carries that id back. Resuming runs
exactly the parked call - the client cannot change what was approved - and
continues the same run instead of replaying the task from the start.

Each park gets a new id and take() removes the run, so an approval can only
be used once: a stale or double-submitted card cannot approve a later call.

Process-local, in-memory state: same single-user tradeoff as
features/audio/player._last_candidates - lost on restart, not shared between
workers.
"""
import secrets
import threading
import time
from dataclasses import dataclass, field

RUN_TTL_SECONDS = 30 * 60
MAX_PAUSED_RUNS = 50


@dataclass
class AgentRun:
    user_input: str
    # Login session the run belongs to - only that session may resume it
    owner: str | None = None
    # External tools the user already approved this session
    granted: set = field(default_factory=set)
    messages: list = field(default_factory=list)
    # Conversation the run belongs to (core/conversations.py) and its earlier
    # turns as chat messages, put before the question
    conversation_id: str | None = None
    history: list = field(default_factory=list)
    # One-line summaries of the tool calls that ran ("edit_file static/styles.css"),
    # stored with the turn so a follow-up knows what was done
    actions: list = field(default_factory=list)
    # Tool calls from the model's last reply that have not been handled yet
    queue: list = field(default_factory=list)
    # The call waiting for approval while the run is parked
    pending: dict | None = None
    # Ollama model running the tool loop (core.llm: the general or the code
    # model), kept so a resumed run continues on the same one
    model: str | None = None
    step: int = 0
    attempted: set = field(default_factory=set)
    unknown_tool_retries: int = 2
    # Month (and day) to open with the final answer, e.g. after creating an event
    show_calendar: dict | None = None
    id: str | None = None
    parked_at: float = 0.0


_lock = threading.Lock()
_paused: dict[str, AgentRun] = {}


def _expire():
    cutoff = time.monotonic() - RUN_TTL_SECONDS
    for run_id in [run_id for run_id, run in _paused.items() if run.parked_at < cutoff]:
        del _paused[run_id]


def park(run):
    """Store a run until the user answers. Returns its new id."""
    with _lock:
        _expire()
        run.id = secrets.token_urlsafe(16)
        run.parked_at = time.monotonic()
        _paused[run.id] = run

        while len(_paused) > MAX_PAUSED_RUNS:
            oldest = min(_paused.values(), key=lambda r: r.parked_at)
            del _paused[oldest.id]

    return run.id


def take(run_id, owner=None):
    """Remove and return a parked run, or None if it is unknown, expired or someone else's."""
    with _lock:
        _expire()
        run = _paused.get(run_id)
        if run is None or run.owner != owner:
            return None
        return _paused.pop(run_id)
