"""JSONL event log (local_storage/logs.txt), one JSON object per line.

The log prunes itself: once it grows past MAX_LOG_BYTES, entries older than
LOG_KEEP_DAYS are dropped, and if it is still over half the limit, the oldest
of the rest too. Run `python -m core.logger` to prune it by age right away.

The CLI and the web server can both log to the same file, so every append and
the prune's rewrite hold a lock file (logs.txt.lock, flock on Linux/macOS,
msvcrt on Windows) - otherwise a line appended while another process rewrites
the file is lost.
"""
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

LOG_FILE = "local_storage/logs.txt"
MAX_LOG_BYTES = 1_000_000
LOG_KEEP_DAYS = 14

# Appends and the prune's rewrite must not interleave (the streaming
# responses log from worker threads).
_lock = threading.Lock()

# The streamed request being served (core/cancel.py sets it): its log lines are
# tagged with it, so a stopped request's lines can be removed again.
request_id_var = ContextVar("request_id", default=None)

LOCK_WAIT_SECONDS = 10


def _lock_file(handle):
    if fcntl:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.01)


def _unlock_file(handle):
    if fcntl:
        fcntl.flock(handle, fcntl.LOCK_UN)
    else:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def _cross_process_lock():
    """Exclusive lock shared by every process that logs to LOG_FILE.

    Best effort: if the lock file can't be opened or locked, logging goes
    ahead unlocked rather than being lost altogether.
    """
    handle = None
    try:
        os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
        handle = open(LOG_FILE + ".lock", "a+")
        _lock_file(handle)
    except OSError as e:
        print(f"[log_event] could not lock {LOG_FILE}: {e}", file=sys.stderr)
        if handle:
            handle.close()
            handle = None
    try:
        yield
    finally:
        if handle:
            try:
                _unlock_file(handle)
            finally:
                handle.close()


def log_event(data):
    if not isinstance(data, dict):
        data = {"message": str(data)}

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        **data
    }
    request_id = request_id_var.get()
    if request_id:
        entry["request_id"] = request_id

    # The log is a diagnostic aid: a full disk or a failed prune must not end
    # the request that was being logged.
    with _lock, _cross_process_lock():
        try:
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
                size = f.tell()
            if size > MAX_LOG_BYTES:
                _prune(LOG_KEEP_DAYS, MAX_LOG_BYTES // 2)
        except OSError as e:
            print(f"[log_event] could not write {LOG_FILE}: {e}", file=sys.stderr)


def _timestamp(line):
    try:
        return datetime.fromisoformat(json.loads(line)["timestamp"])
    except (ValueError, KeyError, TypeError):
        return None


def _prune(keep_days, max_bytes):
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return 0

    cutoff = datetime.now() - timedelta(days=keep_days)
    # A line without a readable timestamp is always kept (it can't be shown to be old)
    kept = [line for line in lines if (_timestamp(line) or cutoff) >= cutoff]

    size = sum(len(line.encode()) for line in kept)
    while kept and size > max_bytes:
        size -= len(kept.pop(0).encode())

    tmp = LOG_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.writelines(kept)
    os.replace(tmp, LOG_FILE)
    return len(lines) - len(kept)


def prune_logs(keep_days=LOG_KEEP_DAYS, max_bytes=MAX_LOG_BYTES):
    """Drop entries older than keep_days, then the oldest until the log fits max_bytes. Returns how many were dropped."""
    with _lock, _cross_process_lock():
        return _prune(keep_days, max_bytes)


def purge_request(request_id):
    """Remove every log line of one request. Returns its tool calls as [(action, args), ...], for the stop reply."""
    tools, kept = [], []
    with _lock, _cross_process_lock():
        try:
            with open(LOG_FILE) as f:
                lines = f.readlines()
        except FileNotFoundError:
            return tools
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                entry = None
            if isinstance(entry, dict) and entry.get("request_id") == request_id:
                if entry.get("type") == "tool_execution":
                    tools.append((entry.get("action"), entry.get("args")))
            else:
                kept.append(line)
        tmp = LOG_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.writelines(kept)
        os.replace(tmp, LOG_FILE)
    return tools


if __name__ == "__main__":
    print(f"Pruned {prune_logs()} entries from {LOG_FILE}.")
