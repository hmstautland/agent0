import json
from datetime import datetime

import agent as agent_mod
import tools.web as webmod
from fastapi.testclient import TestClient
from core.ui import app


def test_llm_direct_answer(monkeypatch):
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt: "Mount Everest is the tallest mountain.")

    result = agent_mod.run_agent("largest mountain")

    assert "Mount Everest" in result


def test_llm_requests_search_web_and_uses_tool(monkeypatch):
    decision_sequence = iter([
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

    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt: next(decision_sequence))
    monkeypatch.setattr(webmod, "search_web", lambda query: [{"title": "Mount Everest", "url": "https://en.wikipedia.org/wiki/Mount_Everest"}])

    result = agent_mod.run_agent("largest mountain", permission_decisions={"search_web": True})

    assert "Found mountains via search_web." in result


def test_stream_agent_shows_calendar_widget_without_a_second_llm_call(monkeypatch):
    # Only one decision is available - if stream_agent fed the calendar
    # result back for a second round (the old behavior: text-summarize it
    # instead of showing the widget), this would raise instead of passing.
    decision_sequence = iter([
        json.dumps({
            "action": "read_calendar",
            "arguments": {},
            "reason": "user asked about their calendar"
        }),
    ])

    def fake_query_llm(prompt, stream=False):
        decision = next(decision_sequence)
        return iter([decision]) if stream else decision

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


def test_run_agent_returns_calendar_events_as_is_for_the_ui_to_render(monkeypatch):
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt: json.dumps({
        "action": "read_calendar",
        "arguments": {},
        "reason": "user asked about their calendar"
    }))
    monkeypatch.setattr(agent_mod, "execute_tool", lambda action, args: [
        {
            "name": "Meeting",
            "date": datetime(2026, 10, 12, 0, 0),
            "end": datetime(2026, 10, 12, 1, 0),
            "description": "",
        }
    ])

    result = agent_mod.run_agent("callendar")

    assert result == [
        {
            "name": "Meeting",
            "date": datetime(2026, 10, 12, 0, 0),
            "end": datetime(2026, 10, 12, 1, 0),
            "description": "",
        }
    ]


def test_ui_permission_flow(monkeypatch):
    # First call: LLM asks for search_web permission.
    monkeypatch.setattr(agent_mod, "query_llm", lambda prompt: json.dumps({
        "action": "search_web",
        "arguments": {"query": "largest mountain"},
        "reason": "To retrieve supporting information"
    }))

    client = TestClient(app)
    response = client.post("/ask", data={"input": "largest mountain"})

    assert response.status_code == 200
    assert "Permission Required" in response.text
    assert "search_web" in response.text

    monkeypatch.setattr(webmod, "search_web", lambda query: [{"title": "Mt. Everest", "url": "https://en.wikipedia.org/wiki/Mount_Everest"}])

    response2 = client.post(
        "/ask",
        data={
            "input": "largest mountain",
            "permission_action": "search_web",
            "permission_decision": "y"
        }
    )

    assert response2.status_code == 200
    assert "Mt. Everest" in response2.text or "Response" in response2.text
