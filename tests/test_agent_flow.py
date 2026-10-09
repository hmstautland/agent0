import json
from datetime import datetime

import agent as agent_mod
import tools.web as webmod
import features.calendar.calendar as calendarmod
import core.auth as auth_mod
from fastapi.testclient import TestClient
from core.ui import app


def test_llm_direct_answer(monkeypatch):
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt, model=None: "Mount Everest is the tallest mountain.")

    result = agent_mod.run_agent("largest mountain")

    assert "Mount Everest" in result


def test_llm_requests_search_web_and_uses_tool(monkeypatch):
    decision_sequence = iter([
        json.dumps({"action": "needs_tools"}),  # local-first: can't answer directly
        json.dumps({
            "action": "search_web",
            "arguments": {"query": "largest mountain"},
            "reason": "find sources"
        }),
        json.dumps({
            "action": "none",
            "response": "Found mountains via search_web."
        })
    ])

    search_calls = []
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt, model=None: next(decision_sequence))
    monkeypatch.setattr(webmod, "search_web", lambda query: search_calls.append(query) or [{"title": "Mount Everest", "url": "https://en.wikipedia.org/wiki/Mount_Everest"}])

    result = agent_mod.run_agent("largest mountain", permission_decisions={"search_web": True})

    assert "Found mountains via search_web." in result
    assert search_calls == ["largest mountain"]


def test_stream_agent_shows_calendar_widget_without_a_second_llm_call(monkeypatch):
    # Only two decisions are available (the local-first check, then the
    # tool choice) - if stream_agent fed the calendar result back for a
    # further round (text-summarizing it instead of showing the widget),
    # this would raise instead of passing.
    decision_sequence = iter([
        json.dumps({"action": "needs_tools"}),
        json.dumps({
            "action": "read_calendar",
            "arguments": {},
            "reason": "user asked about their calendar"
        }),
    ])

    def fake_query_llm(prompt, model=None):
        return next(decision_sequence)

    monkeypatch.setattr(agent_mod, "query_llm", fake_query_llm)
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
    decisions = iter([
        json.dumps({"action": "needs_tools"}),
        json.dumps({
            "action": "read_calendar",
            "arguments": {},
            "reason": "user asked about their calendar"
        }),
    ])
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt, model=None: next(decisions))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: [
        {
            "name": "Meeting",
            "date": datetime(2026, 10, 12, 0, 0),
            "end": datetime(2026, 10, 12, 1, 0),
            "description": "",
        }
    ])

    result = agent_mod.run_agent("callendar")

    assert result == {"show_calendar": {"year": 2026, "month": 10}}


def test_ui_permission_flow(monkeypatch):
    # create_calendar_event is rule="ask" in config/settings.py, so it always
    # requires explicit approval regardless of the local-first check.
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt, model=None: json.dumps({
        "action": "create_calendar_event",
        "arguments": {"title": "Team sync", "start": "2026-09-10 10:00"},
        "reason": "User asked to schedule a meeting"
    }))
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")

    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})

    response = client.post("/ask", data={"input": "schedule a team sync"})

    assert response.status_code == 200
    assert "Permission Required" in response.text
    assert "create_calendar_event" in response.text

    monkeypatch.setattr(calendarmod, "create_event", lambda title, start, end=None, description=None: {"title": title, "start": start})

    response2 = client.post(
        "/ask",
        data={
            "input": "schedule a team sync",
            "permission_action": "create_calendar_event",
            "permission_decision": "y"
        }
    )

    assert response2.status_code == 200
    assert "Team sync" in response2.text or "Response" in response2.text


def test_play_command_bypasses_llm_and_returns_audio_data(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")

    def fail_if_llm_called(prompt, model=None):
        raise AssertionError("play requests must bypass the LLM entirely")

    monkeypatch.setattr(agent_mod, "query_llm", fail_if_llm_called)
    monkeypatch.setattr(
        "core.agent_routes.play_audio_file",
        lambda **kwargs: {"status": "play", "filename": "my-holiday-music.mp3", "audio_url": "/audio/my-holiday-music.mp3"},
    )

    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})

    response = client.post("/ask", data={"input": "play my-holiday-music.mp3"})

    assert response.status_code == 200
    assert "Playing my-holiday-music.mp3" in response.text
    assert "my-holiday-music.mp3" in response.text  # rendered into the audio_data component


def test_play_command_choose_renders_number_buttons(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
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

    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})

    response = client.post("/ask", data={"input": "play music"})

    assert response.status_code == 200
    assert "play number 1" in response.text
    assert "play number 2" in response.text


def test_play_command_via_stream_yields_audio_field(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    monkeypatch.setattr(
        "core.agent_routes.play_audio_file",
        lambda **kwargs: {"status": "play", "filename": "a.wav", "audio_url": "/audio/a.wav"},
    )

    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})

    response = client.post("/ask_stream", data={"input": "play a.wav"})
    event = json.loads(response.text.strip())

    assert event["event"] == "final_response"
    assert event["audio"] == {"status": "play", "filename": "a.wav", "audio_url": "/audio/a.wav"}
