import json

import agent as agent_mod
import tools.web as webmod
import tools.calendar as calendarmod
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
