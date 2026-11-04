"""Stopping a request that is still running (the web UI's stop button).

Each streamed request is registered under an id the browser makes up. POST
/ask_stream/stop with that id marks it cancelled; `scoped` (wrapped around the
event stream) then closes the agent's generator at its next event, which also
closes the open connection to Ollama so the model stops generating, and
removes everything the request left behind: its log lines
(core.logger.purge_request). The turn is never stored, because that happens
only when a final answer arrives.

Limits: the stop takes effect at the next event. While Ollama is still
reading the prompt (before its first token) or a tool is running, that can
take a moment. Tool calls that already ran (a file edit) are not undone; the
stop reply lists them.

Process-local, in-memory state, like core/runs.py.
"""
import socket
import threading
import time
from dataclasses import dataclass, field

from core.logger import purge_request, request_id_var

STOP_WAIT_SECONDS = 5
# A request whose stream was never read (the browser left first) is forgotten after this
REQUEST_TTL_SECONDS = 60 * 60


@dataclass
class ActiveRequest:
    id: str
    owner: str | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    # Set once the request has been wound down; `actions` is then what it had already done
    done: threading.Event = field(default_factory=threading.Event)
    actions: list = field(default_factory=list)
    responses: list = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)


_lock = threading.Lock()
_active: dict[str, ActiveRequest] = {}


def begin(request_id, owner=None):
    request = ActiveRequest(request_id, owner)
    with _lock:
        cutoff = time.monotonic() - REQUEST_TTL_SECONDS
        for stale in [rid for rid, r in _active.items() if r.started < cutoff]:
            del _active[stale]
        _active[request_id] = request
    return request


def finish(request_id):
    with _lock:
        _active.pop(request_id, None)


def stop(request_id, owner=None):
    """Cancel a running request. Returns it, or None if it is unknown, finished or someone else's."""
    with _lock:
        request = _active.get(request_id)
        if request is None or request.owner != owner:
            return None
    request.cancelled.set()
    for response in list(request.responses):
        _abort(response)
    return request


def attach(response):
    """Register an open HTTP response (to Ollama) of the current request, so a stop can cut it off."""
    request = _active.get(request_id_var.get())
    if request is not None:
        request.responses.append(response)
        if request.cancelled.is_set():
            _abort(response)


def detach(response):
    request = _active.get(request_id_var.get())
    if request is not None and response in request.responses:
        request.responses.remove(response)


def _abort(response):
    """Cut the connection from another thread so a read blocked on it fails right away. Best effort."""
    try:
        response.raw._fp.fp.raw._sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        response.close()
    except Exception:
        pass


def scoped(events, request):
    """Pass `events` through with the request id set for logging, ending as soon as the request is cancelled."""
    it = iter(events)
    try:
        while not request.cancelled.is_set():
            token = request_id_var.set(request.id)
            try:
                event = next(it)
            except StopIteration:
                return
            except Exception:
                if request.cancelled.is_set():
                    return  # the abort is what made the call fail
                raise
            finally:
                request_id_var.reset(token)
            if request.cancelled.is_set():
                return
            yield event
    finally:
        token = request_id_var.set(request.id)
        try:
            it.close()
        finally:
            request_id_var.reset(token)
            if request.cancelled.is_set():
                request.actions = purge_request(request.id)
                request.done.set()
            finish(request.id)
