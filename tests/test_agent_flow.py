import json

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
