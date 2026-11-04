import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import agent as agent_mod
import core.auth as auth_mod
import core.cancel as cancel
import core.conversations as conversations
import core.logger as logger
import storage.conversations as store
from core.ui import app


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "logs.txt"
    monkeypatch.setattr(logger, "LOG_FILE", str(path))
    return path


def logged(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_log_lines_of_a_scoped_request_carry_its_id(log_file):
    request = cancel.begin("req-one-1234", owner="me")

    def events():
        logger.log_event({"type": "inside"})
        yield {"event": "status"}

    list(cancel.scoped(events(), request))
    logger.log_event({"type": "outside"})

    assert [(e["type"], e.get("request_id")) for e in logged(log_file)] == [("inside", "req-one-1234"), ("outside", None)]
    assert cancel.stop("req-one-1234", owner="me") is None  # finished requests are forgotten


def test_stopping_closes_the_stream_and_removes_only_that_requests_log_lines(log_file):
    logger.log_event({"type": "earlier_request"})
    request = cancel.begin("req-two-1234", owner="me")
    closed = []

    def events():
        try:
            logger.log_event({"type": "tool_execution", "action": "edit_file", "args": {"path": "a.py"}})
            yield {"event": "status", "message": "one"}
            logger.log_event({"type": "tool_execution", "action": "read_files", "args": {"path": "b.py"}})
            yield {"event": "status", "message": "two"}
            yield {"event": "final_response", "response": "never delivered"}
        finally:
            closed.append(True)

    stream = cancel.scoped(events(), request)
    assert next(stream)["message"] == "one"

    assert cancel.stop("req-two-1234", owner="me") is request
    assert list(stream) == []

    assert closed == [True] and request.done.is_set()
    assert [e["type"] for e in logged(log_file)] == ["earlier_request"]
    assert [name for name, _ in request.actions] == ["edit_file"]


def test_only_the_owner_can_stop_a_request(log_file):
    cancel.begin("req-three-123", owner="me")

    assert cancel.stop("req-three-123", owner="someone-else") is None
    assert cancel.stop("unknown-request", owner="me") is None
    assert cancel.stop("req-three-123", owner="me") is not None
    cancel.finish("req-three-123")


def test_an_error_caused_by_the_abort_is_not_reported_or_raised(log_file):
    request = cancel.begin("req-four-1234", owner="me")

    def events():
        yield {"event": "status"}
        request.cancelled.set()
        raise ConnectionError("socket closed by the stop")

    assert [e["event"] for e in cancel.scoped(events(), request)] == ["status"]


def test_a_stopped_request_is_never_stored_in_the_conversation(log_file):
    request = cancel.begin("req-five-1234", owner="me")

    def events():
        yield {"event": "status"}
        yield {"event": "final_response", "response": "too late"}

    stream = cancel.scoped(conversations.record(events(), "conv-1", "the half-typed question"), request)
    next(stream)
    cancel.stop("req-five-1234", owner="me")
    list(stream)

    assert store.recent_turns("conv-1", 10) == []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    c = TestClient(app)
    c.post("/login", data={"password": "testpass"})
    return c


def test_the_stop_route_ends_a_running_stream_and_cleans_up_after_it(client, log_file, monkeypatch):
    started, closed = threading.Event(), threading.Event()

    def endless_chat(messages, model=None, tools=None, format=None, think=None):
        try:
            for _ in range(400):  # about 8 s unless it is stopped
                started.set()
                yield {"event": "llm_delta", "kind": "content", "text": "."}
                time.sleep(0.02)
        finally:
            closed.set()
        return {"role": "assistant", "content": "done"}

    monkeypatch.setattr(agent_mod, "chat_stream", endless_chat)
    client.post("/ask_stream", data={"input": ""})  # first request: gives the session its id
    stopper = TestClient(app)
    stopper.cookies.update(client.cookies)
    result = {}

    def ask():
        # "a.txt" goes straight to the tool loop, so only the endless chat runs
        result["events"] = client.post("/ask_stream", data={"input": "read a.txt", "request_id": "req-route-1234"}).text

    thread = threading.Thread(target=ask)
    thread.start()
    assert started.wait(5)

    reply = stopper.post("/ask_stream/stop", data={"request_id": "req-route-1234"}).json()
    thread.join(5)

    assert reply["stopped"] and reply["finished"] and reply["already_done"] == []
    assert not thread.is_alive() and closed.is_set()
    assert "final_response" not in result["events"]
    assert not any(e.get("request_id") == "req-route-1234" for e in logged(log_file))
    assert store.recent_turns(conversations.new_conversation(), 5) == []


def test_stopping_an_unknown_request_does_nothing(client):
    assert client.post("/ask_stream/stop", data={"request_id": "never-started-1"}).json() == {"stopped": False}
    assert client.post("/ask_stream/stop", data={}).json() == {"stopped": False}


def test_a_malformed_request_id_is_ignored_instead_of_registered(client, monkeypatch):
    seen = []
    monkeypatch.setattr(cancel, "begin", lambda *a, **k: seen.append(a) or cancel.ActiveRequest("x"))

    client.post("/ask_stream", data={"input": "", "request_id": "bad id with spaces!"})

    assert seen == []
