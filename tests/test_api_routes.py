import core.auth as auth_mod
from core import llm
from fastapi.testclient import TestClient

from core.ui import app
from features.api.common import EXPLAIN_FLAG, LOOKUP_FLAG
from storage import conversations
from storage import integrations as flags

KEY = "test-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}
EXPLAIN = {"subject": "AAPL buy signal", "facts": {"RSI": 32.1, "SMA20": 185.40, "SMA50": 182.10}}
LOOKUP = {"query": "what sector is NVDA?", "context": {"holdings": ["AAPL", "MSFT"]}}


def _stub_chat(monkeypatch, content="Looks like a decent setup."):
    calls = []

    def chat(messages, **kwargs):
        calls.append((messages, kwargs))
        return {"content": content}

    monkeypatch.setattr(llm, "chat", chat)
    return calls


def _client(monkeypatch, enabled=True, key=KEY, explain=None, lookup=None):
    """Both endpoints on/off together via `enabled`, or each one via explain=/lookup=."""
    if key:
        monkeypatch.setenv("AGENT_API_KEY", key)
    else:
        monkeypatch.delenv("AGENT_API_KEY", raising=False)
    flags.set_enabled(EXPLAIN_FLAG, enabled if explain is None else explain)
    flags.set_enabled(LOOKUP_FLAG, enabled if lookup is None else lookup)
    return TestClient(app)


def test_off_by_default_blocks_both_endpoints_without_calling_the_model(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", KEY)
    calls = _stub_chat(monkeypatch)
    client = TestClient(app)
    for path, body in (("/api/v1/explain", EXPLAIN), ("/api/v1/lookup", LOOKUP)):
        r = client.post(path, json=body, headers=AUTH)
        assert r.status_code == 403
        assert r.json() == {"detail": "integration disabled"}
    assert calls == []


def test_unset_key_disables_api(monkeypatch):
    client = _client(monkeypatch, key=None)
    assert client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH).status_code == 503


def test_missing_or_wrong_key_is_401_json_even_when_flag_off(monkeypatch):
    for enabled in (True, False):
        client = _client(monkeypatch, enabled=enabled)
        for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": KEY}):
            r = client.post("/api/v1/lookup", json=LOOKUP, headers=headers, follow_redirects=False)
            assert r.status_code == 401
            assert r.json()["detail"]


def test_explain_uses_default_model_no_tools_and_includes_facts(monkeypatch):
    calls = _stub_chat(monkeypatch)
    client = _client(monkeypatch)
    r = client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["explanation"] == "Looks like a decent setup."
    messages, kwargs = calls[0]
    assert "tools" not in kwargs and "model" not in kwargs
    assert "AAPL buy signal" in messages[1]["content"] and "185.4" in messages[1]["content"]


def test_lookup_includes_context_and_uses_no_tools(monkeypatch):
    calls = _stub_chat(monkeypatch, "Technology.")
    client = _client(monkeypatch)
    r = client.post("/api/v1/lookup", json=LOOKUP, headers=AUTH)
    assert r.status_code == 200 and r.json()["answer"] == "Technology."
    messages, kwargs = calls[0]
    assert "tools" not in kwargs and "model" not in kwargs
    assert "MSFT" in messages[1]["content"] and "what sector is NVDA?" in messages[1]["content"]


def test_lookup_without_context(monkeypatch):
    calls = _stub_chat(monkeypatch)
    client = _client(monkeypatch)
    assert client.post("/api/v1/lookup", json={"query": "hi"}, headers=AUTH).status_code == 200
    assert "CONTEXT" not in calls[0][0][1]["content"]


def test_bad_style_and_bad_body_are_422(monkeypatch):
    _stub_chat(monkeypatch)
    client = _client(monkeypatch)
    assert client.post("/api/v1/explain", json={**EXPLAIN, "style": "x"}, headers=AUTH).status_code == 422
    assert client.post("/api/v1/lookup", json={}, headers=AUTH).status_code == 422


def test_model_down_is_502_without_leaking_details(monkeypatch):
    def chat(messages, **kwargs):
        raise llm.LLMError("Could not reach Ollama at http://secret")

    monkeypatch.setattr(llm, "chat", chat)
    client = _client(monkeypatch)
    r = client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH)
    assert r.status_code == 502 and "secret" not in r.text


def test_api_calls_are_not_stored_in_conversation_memory(monkeypatch):
    _stub_chat(monkeypatch)
    client = _client(monkeypatch)
    client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH)
    client.post("/api/v1/lookup", json=LOOKUP, headers=AUTH)
    assert conversations.search_turns("sector") == []


def test_each_endpoint_has_its_own_flag(monkeypatch):
    calls = _stub_chat(monkeypatch)
    client = _client(monkeypatch, explain=True, lookup=False)
    assert client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH).status_code == 200
    r = client.post("/api/v1/lookup", json=LOOKUP, headers=AUTH)
    assert r.status_code == 403 and r.json() == {"detail": "integration disabled"}
    assert len(calls) == 1

    calls.clear()
    client = _client(monkeypatch, explain=False, lookup=True)
    assert client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH).status_code == 403
    assert client.post("/api/v1/lookup", json=LOOKUP, headers=AUTH).status_code == 200
    assert len(calls) == 1


def test_old_combined_flag_no_longer_opens_anything(monkeypatch):
    calls = _stub_chat(monkeypatch)
    client = _client(monkeypatch, enabled=False)
    flags.set_enabled("trading-signals", True)  # the pre-split combined flag
    assert client.post("/api/v1/explain", json=EXPLAIN, headers=AUTH).status_code == 403
    assert client.post("/api/v1/lookup", json=LOOKUP, headers=AUTH).status_code == 403
    assert calls == []


def test_every_api_endpoint_is_blocked_when_all_flags_are_off(monkeypatch):
    """Walks the published routes, so a future endpoint added without its own flag fails here."""
    calls = _stub_chat(monkeypatch)
    client = _client(monkeypatch, enabled=False)
    found = 0
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method in methods:
            found += 1
            r = client.request(method.upper(), path, json={}, headers=AUTH)
            assert r.status_code == 403, f"{method.upper()} {path} is not behind a flag"
    assert found >= 2 and calls == []


def test_openapi_schema_builds_without_warnings_and_hides_the_audio_file_server():
    import warnings

    app.openapi_schema = None  # force a rebuild so duplicate operation ids would warn
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        paths = app.openapi()["paths"]
    assert "/audio/{path}" not in paths
