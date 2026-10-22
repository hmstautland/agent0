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
    """chat_stream() stand-in: returns the given assistant messages in order and records every call.

    Streams each reply's content as one llm_delta first, like Ollama would.
    """
    queue = list(replies)
    calls = []

    def chat(messages, model=None, tools=None, format=None, think=None):
        calls.append({"messages": [dict(m) for m in messages], "tools": tools, "format": format})
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply.get("content"):
            yield {"event": "llm_delta", "kind": "content", "text": reply["content"]}
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
    monkeypatch.setattr(agent_mod, "_cli_conversation", None)


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
    monkeypatch.setattr(agent_mod, "chat_stream", chat)

    result = agent_mod.run_agent("largest mountain")

    assert "Mount Everest" in result
    assert len(chat.calls) == 1
    assert chat.calls[0]["format"] == agent_mod.LOCAL_ANSWER_FORMAT


def test_cli_tool_loop_uses_native_tool_calls_and_feeds_results_back(monkeypatch):
    chat = fake_chat(local("needs_tools"), tool_call("search_web", query="largest mountain"), answer("Found mountains via search_web."))
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    search_calls = []
    monkeypatch.setattr(webmod, "search_web", lambda query: search_calls.append(query) or [{"title": "Mount Everest"}])

    result = agent_mod.run_agent("largest mountain")

    assert result == "Found mountains via search_web."
    assert search_calls == ["largest mountain"]
    assert {t["function"]["name"] for t in chat.calls[1]["tools"]} == set(agent_mod.TOOLS)
    assert "Mount Everest" in tool_messages(chat.calls[2])[0]["content"]


def test_cli_asks_for_an_external_tool_once_per_session(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(
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
    monkeypatch.setattr(agent_mod, "chat_stream", chat)

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
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append((action, args)) or ["core/auth.py"])

    assert agent_mod.run_agent("which file checks the login") == "It is in core/auth.py."
    assert executed == [("search_files", {"keyword": "login"})]
    assert chat.calls[1]["messages"][-2]["content"] == "I'll search for it."


def test_ollama_down_gives_an_error_event(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(LLMError("Could not reach Ollama")))

    events = list(agent_mod.stream_agent("hello"))

    assert last(events) == {"event": "error", "message": "Could not reach Ollama"}


def test_repeat_guard_allows_verify_again_after_an_edit(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(
        tool_call("verify_app"), tool_call("edit_file", path="a.html", old_text="x", new_text="y"),
        tool_call("verify_app"), answer("done"),
    ))
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append(action) or "OK")

    assert agent_mod.run_agent("fix the template") == "done"
    assert executed == ["verify_app", "edit_file", "verify_app"]


def test_stream_agent_streams_llm_text_before_the_final_answer(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(local("none", "Paris.")))

    events = list(agent_mod.stream_agent("capital of france?"))

    deltas = [e for e in events if e["event"] == "llm_delta"]
    assert "".join(d["text"] for d in deltas) == "Paris."  # the answer text, not the JSON envelope
    assert events.index(deltas[-1]) < events.index(last(events))
    assert last(events) == {"event": "final_response", "response": "Paris."}


def test_stream_agent_shows_calendar_widget_without_a_second_llm_call(monkeypatch):
    # Only two replies are available (the local-first check, then the tool
    # choice) - if the calendar result were fed back for another round
    # (text-summarizing it instead of showing the widget), this would fail.
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(local("needs_tools"), tool_call("read_calendar")))
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
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(local("needs_tools"), tool_call("read_calendar")))
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
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
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
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(
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
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(tool_call("write_file", path="a.txt", content="x"), answer("done")))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: "OK")

    paused = last(stream(client, input="write file a.txt"))

    other = TestClient(app)
    other.post("/login", data={"password": "testpass"})
    assert last(stream(other, run_id=paused["run_id"], permission_decision="y"))["event"] == "error"

    assert last(stream(client, run_id=paused["run_id"], permission_decision="y"))["event"] == "final_response"
    assert last(stream(client, run_id=paused["run_id"], permission_decision="y"))["event"] == "error"


def test_denied_call_is_reported_to_the_model_instead_of_run(monkeypatch, client):
    chat = fake_chat(tool_call("write_file", path="a.txt", content="x"), answer("I did not write a.txt."))
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
    executed = []
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: executed.append(action))

    paused = last(stream(client, input="write file a.txt"))
    final = last(stream(client, run_id=paused["run_id"], permission_decision="n"))

    assert final["response"] == "I did not write a.txt."
    assert executed == []
    assert "denied" in tool_messages(chat.calls[1])[0]["content"]


def test_external_tool_approval_is_kept_for_the_login_session(monkeypatch, client):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(
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
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(
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

    monkeypatch.setattr(agent_mod, "chat_stream", fail_if_llm_called)
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


@pytest.mark.parametrize("text", [
    "what is a project manager",
    "what is the project manager's job",
    "explain what a repository is",
    "what is a file system",
    "tell me about my day",
    "Where can I buy a used car?",
    "where do I set up a new bank account",
])
def test_plain_questions_are_not_routed_straight_to_the_tool_loop(text):
    assert not agent_mod.needs_tools(text)


@pytest.mark.parametrize("text", [
    "fix the template",
    "which file checks the login",
    "list project files",
    "create static/new.js and include it in the template",
    "read this codebase",
    "write file a.txt",
    "Where is MAX_STEPS defined and how is it used?",
    "what does run_agent do",
    "what does needs_tools() return",
    "where is the step limit configured",
    "where is the retry limit defined",
])
def test_file_tasks_skip_the_local_first_step(text):
    assert agent_mod.needs_tools(text)


def test_tool_loop_sends_a_pruned_history_to_the_model_but_keeps_the_full_one(monkeypatch):
    chat = fake_chat(
        local("needs_tools"),
        tool_call("search_web", query="a"), tool_call("search_web", query="b"), tool_call("search_web", query="c"),
        answer("done"),
    )
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    monkeypatch.setattr(webmod, "search_web", lambda query: [{"snippet": query * 3000}])
    monkeypatch.setattr(
        agent_mod, "prune_messages", lambda messages: agent_mod.context.prune_messages(messages, budget=1500)
    )

    assert agent_mod.run_agent("search for stuff") == "done"

    sent = [m["content"] for m in tool_messages(chat.calls[-1])]
    assert sent[0].startswith("[earlier search_web result trimmed")
    assert "ccc" in sent[-1]


def test_each_model_step_reports_how_long_it_took_and_how_much_it_was_sent(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(local("needs_tools"), tool_call("search_web", query="a"), answer("done")))
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    monkeypatch.setattr(webmod, "search_web", lambda query: [{"title": "x"}])
    events = []
    monkeypatch.setattr(agent_mod, "log_event", events.append)

    agent_mod.run_agent("search for a")

    timings = [e for e in events if e["type"] == "step_timing"]
    assert [t["step"] for t in timings] == [1, 2]
    assert all(t["llm_seconds"] >= 0 and t["est_tokens_in"] > 0 for t in timings)
    assert all("seconds" in e for e in events if e["type"] == "tool_execution")


def test_a_follow_up_question_is_sent_the_earlier_turns_and_what_their_tools_did(monkeypatch, client):
    chat = fake_chat(
        tool_call("edit_file", path="static/styles.css", old_text="a", new_text="b"),
        answer("Added a light mode to static/styles.css."),
        local("needs_tools"),
        answer("Made the light background grey."),
    )
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: "OK")

    parked = last(stream(client, input="edit the UI in static/styles.css to support light mode"))
    assert last(stream(client, run_id=parked["run_id"], permission_decision="y"))["event"] == "final_response"

    stream(client, input="change the light background color to a light grey")

    local_first = chat.calls[2]["messages"]
    assert [m["role"] for m in local_first] == ["system", "user", "assistant", "user"]
    assert local_first[1]["content"] == "edit the UI in static/styles.css to support light mode"
    assert local_first[2]["content"] == (
        "[Tools used: edit_file static/styles.css]\nAdded a light mode to static/styles.css."
    )
    tool_loop = chat.calls[3]["messages"]
    assert tool_loop[0]["role"] == "system"
    assert tool_loop[1:3] == local_first[1:3]
    assert tool_loop[-1]["content"] == "change the light background color to a light grey"


def test_new_chat_forgets_the_earlier_turns(monkeypatch, client):
    chat = fake_chat(local("none", "Hi!"), local("none", "Hello again."))
    monkeypatch.setattr(agent_mod, "chat_stream", chat)

    stream(client, input="hello")
    assert client.post("/conversation/new").json() == {"ok": True}
    stream(client, input="hello?")

    assert [m["role"] for m in chat.calls[1]["messages"]] == ["system", "user"]


def test_shortcuts_are_part_of_the_conversation(monkeypatch, client):
    monkeypatch.setattr("core.agent_routes.save_note_text", lambda text, source: "local_storage/note_1.txt")
    chat = fake_chat(local("none", "It said: buy milk."))
    monkeypatch.setattr(agent_mod, "chat_stream", chat)

    stream(client, input="note: buy milk")
    stream(client, input="what did that note say?")

    history = chat.calls[0]["messages"][1:3]
    assert history[0]["content"] == "note: buy milk"
    assert history[1]["content"] == "Note saved to local_storage/note_1.txt"


def test_cli_keeps_one_conversation_until_new(monkeypatch):
    chat = fake_chat(local("none", "Hi!"), local("none", "Again."), local("none", "Fresh."))
    monkeypatch.setattr(agent_mod, "chat_stream", chat)

    agent_mod.run_agent("hello")
    agent_mod.run_agent("hello again")
    agent_mod.cli_conversation_id(new=True)
    agent_mod.run_agent("hello?")

    assert [len(c["messages"]) for c in chat.calls] == [2, 4, 2]


@pytest.mark.parametrize("value", ["", "eight", "  "])
def test_a_bad_env_value_falls_back_to_the_default_instead_of_crashing(monkeypatch, value):
    from config.settings import env_int

    monkeypatch.setenv("SOME_LIMIT", value)

    assert env_int("SOME_LIMIT", 8) == 8
    monkeypatch.setenv("SOME_LIMIT", "12")
    assert env_int("SOME_LIMIT", 8) == 12


def test_local_first_call_shows_nothing_when_the_model_asks_for_tools(monkeypatch):
    monkeypatch.setattr(agent_mod, "chat_stream", fake_chat(local("needs_tools")))

    events = list(agent_mod.try_local_answer("anything"))

    assert [e for e in events if e.get("kind") == "content"] == []


def test_local_first_stream_decodes_escapes_and_passes_thinking_through(monkeypatch):
    def chat(messages, model=None, tools=None, format=None, think=None):
        yield {"event": "llm_delta", "kind": "thinking", "text": "hmm"}
        for piece in ('{"action":"none","response":"say \\"h', 'i\\"\\nbye', '"}'):
            yield {"event": "llm_delta", "kind": "content", "text": piece}
        return {"role": "assistant", "content": '{"action":"none","response":"say \\"hi\\"\\nbye"}'}

    monkeypatch.setattr(agent_mod, "chat_stream", chat)

    gen = agent_mod.try_local_answer("q")
    events = []
    while True:
        try:
            events.append(next(gen))
        except StopIteration as done:
            result = done.value
            break

    assert [e["text"] for e in events if e["kind"] == "thinking"] == ["hmm"]
    assert "".join(e["text"] for e in events if e["kind"] == "content") == 'say "hi"\nbye'
    assert result == 'say "hi"\nbye'


@pytest.mark.parametrize("result", [
    "ERROR: no such tool", "Access denied: .env holds secrets", "File not found",
    "old_text not found in file - read the file again", "old_text appears 2 times - include more", "No files matched ['x']",
])
def test_results_that_report_failure_are_recognised(result):
    assert agent_mod._reported_failure(result)


@pytest.mark.parametrize("result", ["File edited: a.py (previous version saved as x)", "File created: a.py", ["a.py"], {"a.py": "text"}, ""])
def test_successful_results_are_not_marked_failed(result):
    assert not agent_mod._reported_failure(result)


def test_a_failed_edit_is_recorded_as_failed_in_the_turn_history(monkeypatch):
    # "a.py" routes straight to the tool loop, so there is no local-first reply
    chat = fake_chat(tool_call("edit_file", path="a.py", old_text="x", new_text="y"), answer("Could not change it."))
    monkeypatch.setattr(agent_mod, "chat_stream", chat)
    monkeypatch.setattr(agent_mod, "ask_cli", lambda *a, **k: True)
    monkeypatch.setattr(agent_mod, "execute_tool", lambda name, args: "old_text not found in file - read the file again")
    run = agent_mod.AgentRun(user_input="edit a.py")

    list(agent_mod._run_steps(run, interactive=True))

    assert run.actions == ["edit_file a.py (failed)"]
