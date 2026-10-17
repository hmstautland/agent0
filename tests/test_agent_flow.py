import json
from datetime import datetime

import pytest

import agent as agent_mod
import tools.web as webmod
import features.calendar.calendar as calendarmod
import core.auth as auth_mod
from core.llm import LLMError
from fastapi.testclient import TestClient
from core.ui import app


def fake_chat(*replies):
    """chat() stand-in: returns the given assistant messages in order and records every call."""
    queue = list(replies)
    calls = []

    def chat(messages, model=None, tools=None, format=None, think=None):
        calls.append({"messages": [dict(m) for m in messages], "tools": tools, "format": format})
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    chat.calls = calls
    return chat


def answer(text):
    return {"role": "assistant", "content": text}


def local(action, response=None):
    return answer(json.dumps({"action": action, "response": response} if response else {"action": action}))


def tool_call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def tool_messages(call):
    return [m for m in call["messages"] if m["role"] == "tool"]


@pytest.fixture(autouse=True)
def no_logging(monkeypatch):
    monkeypatch.setattr(agent_mod, "log_event", lambda event: None)
    monkeypatch.setattr("core.agent_routes.log_event", lambda event: None)
    agent_mod._cli_granted.clear()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    c = TestClient(app)
    c.post("/login", data={"password": "testpass"})
    return c


def stream(client, **data):
    response = client.post("/ask_stream", data=data)
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def last(events):
    return events[-1]


def test_llm_direct_answer(monkeypatch):
    chat = fake_chat(local("none", "Mount Everest is the tallest mountain."))
    monkeypatch.setattr(agent_mod, "chat", chat)

    result = agent_mod.run_agent("largest mountain")

    assert "Mount Everest" in result
    assert len(chat.calls) == 1
    assert chat.calls[0]["format"] == agent_mod.LOCAL_ANSWER_FORMAT


def test_cli_tool_loop_uses_native_tool_calls_and_feeds_results_back(monkeypatch):
    chat = fake_chat(local("needs_tools"), tool_call("search_web", query="largest mountain"), answer("Found mountains via search_web."))
    monkeypatch.setattr(agent_mod, "chat", chat)
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    search_calls = []
    monkeypatch.setattr(webmod, "search_web", lambda query: search_calls.append(query) or [{"title": "Mount Everest"}])

    result = agent_mod.run_agent("largest mountain")

    assert result == "Found mountains via search_web."
    assert search_calls == ["largest mountain"]
    assert {t["function"]["name"] for t in chat.calls[1]["tools"]} == set(agent_mod.TOOLS)
    assert "Mount Everest" in tool_messages(chat.calls[2])[0]["content"]


def test_cli_asks_for_an_external_tool_once_per_session(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat", fake_chat(
        local("needs_tools"), tool_call("search_web", query="a"), answer("one"),
        local("needs_tools"), tool_call("search_web", query="b"), answer("two"),
    ))
    asked = []
    monkeypatch.setattr(agent_mod, "ask_cli", lambda action, *a, **k: asked.append(action) or True)
    monkeypatch.setattr(webmod, "search_web", lambda query: [])

    assert agent_mod.run_agent("first") == "one"
    assert agent_mod.run_agent("second") == "two"
    assert asked == ["search_web"]


def test_tool_exception_is_handed_back_to_the_model(monkeypatch):
    chat = fake_chat(local("needs_tools"), tool_call("read_calendar", month="october"), answer("Sorry, fixed it."))
    monkeypatch.setattr(agent_mod, "chat", chat)

    result = agent_mod.run_agent("what's on in october")

    assert result == "Sorry, fixed it."
    error = tool_messages(chat.calls[2])[0]["content"]
    assert error.startswith("ERROR TypeError") and "read_calendar takes ()" in error


def test_tool_call_written_as_qwen_markup_in_the_text_is_still_run(monkeypatch):
    # What qwen3-coder sends when Ollama fails to extract its call
    markup = (
        "I'll search for it.\n\n<function=search_files>\n<parameter=keyword>\nlogin\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    chat = fake_chat(answer(markup), answer("It is in core/auth.py."))
    monkeypatch.setattr(agent_mod, "chat", chat)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append((action, args)) or ["core/auth.py"])

    assert agent_mod.run_agent("which file checks the login") == "It is in core/auth.py."
    assert executed == [("search_files", {"keyword": "login"})]
    assert chat.calls[1]["messages"][-2]["content"] == "I'll search for it."


def test_ollama_down_gives_an_error_event(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat", fake_chat(LLMError("Could not reach Ollama")))

    events = list(agent_mod.stream_agent("hello"))

    assert last(events) == {"event": "error", "message": "Could not reach Ollama"}


def test_repeat_guard_allows_verify_again_after_an_edit(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat", fake_chat(
        tool_call("verify_app"), tool_call("edit_file", path="a.html", old_text="x", new_text="y"),
        tool_call("verify_app"), answer("done"),
    ))
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append(action) or "OK")

    assert agent_mod.run_agent("fix the template") == "done"
    assert executed == ["verify_app", "edit_file", "verify_app"]


def test_stream_agent_shows_calendar_widget_without_a_second_llm_call(monkeypatch):
    # Only two replies are available (the local-first check, then the tool
    # choice) - if the calendar result were fed back for another round
    # (text-summarizing it instead of showing the widget), this would fail.
    monkeypatch.setattr(agent_mod, "chat", fake_chat(local("needs_tools"), tool_call("read_calendar")))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: [
        {
            "name": "Meeting",
            "date": datetime(2026, 10, 12, 0, 0),
            "end": datetime(2026, 10, 12, 1, 0),
            "description": "",
        }
    ])

    events = list(agent_mod.stream_agent("callendar"))

    final_events = [e for e in events if e["event"] == "final_response"]
    assert len(final_events) == 1
    assert final_events[0]["show_calendar"] == {"year": 2026, "month": 10}


def test_run_agent_hands_the_calendar_month_to_the_caller_for_the_ui_to_render(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat", fake_chat(local("needs_tools"), tool_call("read_calendar")))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: [
        {
            "name": "Meeting",
            "date": datetime(2026, 10, 12, 0, 0),
            "end": datetime(2026, 10, 12, 1, 0),
            "description": "",
        }
    ])

    assert agent_mod.run_agent("callendar") == {"show_calendar": {"year": 2026, "month": 10}}


def test_resumed_run_executes_each_approved_call_once_and_continues(monkeypatch, client):
    # Two different "ask" tools in one task used to loop forever, re-running
    # the first write on every approval.
    chat = fake_chat(
        tool_call("write_file", path="static/new.js", content="x"),
        tool_call("edit_file", path="templates/index.html", old_text="a", new_text="b"),
        answer("Created static/new.js and linked it."),
    )
    monkeypatch.setattr(agent_mod, "chat", chat)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append((action, args)) or "OK")

    first = last(stream(client, input="create static/new.js and include it in the template"))
    assert first["event"] == "permission_required" and first["action"] == "write_file"

    second = last(stream(client, run_id=first["run_id"], permission_decision="y"))
    assert second["event"] == "permission_required" and second["action"] == "edit_file"
    assert second["run_id"] != first["run_id"]

    third = last(stream(client, run_id=second["run_id"], permission_decision="y"))
    assert third == {"event": "final_response", "response": "Created static/new.js and linked it."}
    assert executed == [
        ("write_file", {"path": "static/new.js", "content": "x"}),
        ("edit_file", {"path": "templates/index.html", "old_text": "a", "new_text": "b"}),
    ]
    assert len(chat.calls) == 3


def test_approving_a_call_does_not_approve_the_same_tool_with_other_args(monkeypatch, client):
    # Approving write_file for notes/a.txt used to also approve a later
    # write_file of core/ui.py in the same run.
    monkeypatch.setattr(agent_mod, "chat", fake_chat(
        tool_call("write_file", path="notes/a.txt", content="hi"),
        tool_call("write_file", path="core/ui.py", content="evil"),
        answer("done"),
    ))
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append(args["path"]) or "OK")

    first = last(stream(client, input="write file notes/a.txt"))
    second = last(stream(client, run_id=first["run_id"], permission_decision="y"))

    assert second["event"] == "permission_required"
    assert second["args"] == {"path": "core/ui.py", "content": "evil"}
    assert executed == ["notes/a.txt"]

    assert last(stream(client, run_id=second["run_id"], permission_decision="n"))["response"] == "done"
    assert executed == ["notes/a.txt"]


def test_an_approval_can_only_be_used_once_and_only_by_its_session(monkeypatch, client):
    monkeypatch.setattr(agent_mod, "chat", fake_chat(tool_call("write_file", path="a.txt", content="x"), answer("done")))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: "OK")

    paused = last(stream(client, input="write file a.txt"))

    other = TestClient(app)
    other.post("/login", data={"password": "testpass"})
    assert last(stream(other, run_id=paused["run_id"], permission_decision="y"))["event"] == "error"

    assert last(stream(client, run_id=paused["run_id"], permission_decision="y"))["event"] == "final_response"
    assert last(stream(client, run_id=paused["run_id"], permission_decision="y"))["event"] == "error"


def test_denied_call_is_reported_to_the_model_instead_of_run(monkeypatch, client):
    chat = fake_chat(tool_call("write_file", path="a.txt", content="x"), answer("I did not write a.txt."))
    monkeypatch.setattr(agent_mod, "chat", chat)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append(action))

    paused = last(stream(client, input="write file a.txt"))
    final = last(stream(client, run_id=paused["run_id"], permission_decision="n"))

    assert final["response"] == "I did not write a.txt."
    assert executed == []
    assert "denied" in tool_messages(chat.calls[1])[0]["content"]


def test_external_tool_approval_is_kept_for_the_login_session(monkeypatch, client):
    monkeypatch.setattr(agent_mod, "chat", fake_chat(
        local("needs_tools"), tool_call("search_web", query="a"), answer("one"),
        local("needs_tools"), tool_call("search_web", query="b"), answer("two"),
        local("needs_tools"), tool_call("search_web", query="c"),
    ))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: [])

    paused = last(stream(client, input="news about mountains"))
    assert paused["action"] == "search_web" and paused["external"] is True
    assert last(stream(client, run_id=paused["run_id"], permission_decision="y"))["response"] == "one"

    # Same session: no second prompt
    assert last(stream(client, input="news about rivers"))["response"] == "two"

    # After logging out the approval is gone
    client.post("/logout")
    client.post("/login", data={"password": "testpass"})
    assert last(stream(client, input="news about lakes"))["event"] == "permission_required"


def test_ui_permission_flow_plain_form(monkeypatch, client):
    # create_calendar_event is rule="ask" in config/settings.py, so it always
    # requires explicit approval regardless of the local-first check.
    monkeypatch.setattr(agent_mod, "chat", fake_chat(
        local("needs_tools"),
        tool_call("create_calendar_event", title="Team sync", start="2026-09-10 10:00"),
        answer("Team sync is booked."),
    ))
    created = []
    monkeypatch.setattr(calendarmod, "create_event", lambda title, start, end=None, description=None: created.append(title) or "added")

    response = client.post("/ask", data={"input": "schedule a team sync"})

    assert response.status_code == 200
    assert "Permission Required" in response.text
    assert "create_calendar_event" in response.text
    run_id = response.text.split('name="run_id" id="perm-run-id" value="')[1].split('"')[0]

    response2 = client.post("/ask", data={"run_id": run_id, "permission_decision": "y"})

    assert response2.status_code == 200
    assert "Team sync is booked." in response2.text
    assert created == ["Team sync"]


def test_play_command_bypasses_llm_and_returns_audio_data(monkeypatch, client):
    def fail_if_llm_called(*args, **kwargs):
        raise AssertionError("play requests must bypass the LLM entirely")

    monkeypatch.setattr(agent_mod, "chat", fail_if_llm_called)
    monkeypatch.setattr(
        "core.agent_routes.play_audio_file",
        lambda **kwargs: {"status": "play", "filename": "my-holiday-music.mp3", "audio_url": "/audio/my-holiday-music.mp3"},
    )

    response = client.post("/ask", data={"input": "play my-holiday-music.mp3"})

    assert response.status_code == 200
    assert "Playing my-holiday-music.mp3" in response.text
    assert "my-holiday-music.mp3" in response.text  # rendered into the audio_data component


def test_play_command_choose_renders_number_buttons(monkeypatch, client):
    monkeypatch.setattr(
        "core.agent_routes.play_audio_file",
        lambda **kwargs: {
            "status": "choose",
            "candidates": [
                {"number": 1, "filename": "my-holiday-music.mp3", "audio_url": "/audio/my-holiday-music.mp3"},
                {"number": 2, "filename": "my-other-music.mp3", "audio_url": "/audio/my-other-music.mp3"},
            ],
        },
    )

    response = client.post("/ask", data={"input": "play music"})

    assert response.status_code == 200
    assert "play number 1" in response.text
    assert "play number 2" in response.text


def test_play_command_via_stream_yields_audio_field(monkeypatch, client):
    monkeypatch.setattr(
        "core.agent_routes.play_audio_file",
        lambda **kwargs: {"status": "play", "filename": "a.wav", "audio_url": "/audio/a.wav"},
    )

    event = last(stream(client, input="play a.wav"))

    assert event["event"] == "final_response"
    assert event["audio"] == {"status": "play", "filename": "a.wav", "audio_url": "/audio/a.wav"}
