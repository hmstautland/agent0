import core.auth as auth_mod
from fastapi.testclient import TestClient

from core.ui import app
from features.api.common import EXPLAIN_FLAG, LOOKUP_FLAG
from storage import integrations as flags


def _logged_in(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})
    return client


def test_config_requires_login(monkeypatch):
    client = TestClient(app)
    for r in (
        client.get("/config", follow_redirects=False),
        client.post(f"/config/integrations/{EXPLAIN_FLAG}", data={"enabled": "1"}, follow_redirects=False),
    ):
        assert r.status_code == 303 and r.headers["location"] == "/login"
    assert flags.is_enabled(EXPLAIN_FLAG) is False


def test_page_lists_integration_and_decisions_but_never_the_key(monkeypatch):
    monkeypatch.setenv("AGENT_API_KEY", "super-secret-key-value")
    client = _logged_in(monkeypatch)
    page = client.get("/config")
    assert page.status_code == 200
    assert "Trading signals (Kush app): Explain" in page.text and "Trading signals (Kush app): Lookup" in page.text
    assert "POST /api/v1/explain" in page.text and "POST /api/v1/lookup" in page.text
    assert "No permission grants anywhere" in page.text
    assert "API key configured" in page.text
    assert "super-secret-key-value" not in page.text


def test_page_warns_when_key_is_not_set(monkeypatch):
    monkeypatch.delenv("AGENT_API_KEY", raising=False)
    assert "API key not configured" in _logged_in(monkeypatch).get("/config").text


def test_toggle_on_and_off(monkeypatch):
    client = _logged_in(monkeypatch)
    r = client.post(f"/config/integrations/{EXPLAIN_FLAG}", data={"enabled": "1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/config"
    assert flags.is_enabled(EXPLAIN_FLAG) is True
    client.post(f"/config/integrations/{EXPLAIN_FLAG}", data={"enabled": "0"})
    assert flags.is_enabled(EXPLAIN_FLAG) is False


def test_toggling_one_endpoint_leaves_the_other_alone(monkeypatch):
    client = _logged_in(monkeypatch)
    client.post(f"/config/integrations/{LOOKUP_FLAG}", data={"enabled": "1"})
    assert flags.is_enabled(LOOKUP_FLAG) is True
    assert flags.is_enabled(EXPLAIN_FLAG) is False


def test_each_card_has_its_own_decisions(monkeypatch):
    page = _logged_in(monkeypatch).get("/config").text
    assert page.count("No permission grants anywhere") == 2
    assert page.count("Lookup uses none of agent0") == 1


def test_unknown_integration_is_404(monkeypatch):
    client = _logged_in(monkeypatch)
    assert client.post("/config/integrations/nope", data={"enabled": "1"}).status_code == 404


def test_chat_page_has_config_link(monkeypatch):
    client = _logged_in(monkeypatch)
    assert 'href="/config"' in client.get("/").text


def test_api_docs_and_schema_need_login(monkeypatch):
    client = TestClient(app)
    for path in ("/config/api-docs", "/config/api-openapi.json"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_api_docs_page_and_filtered_schema_when_logged_in(monkeypatch):
    client = _logged_in(monkeypatch)
    page = client.get("/config/api-docs")
    assert page.status_code == 200 and "swagger-ui" in page.text and "/config/api-openapi.json" in page.text
    assert "/config/api-docs" in client.get("/config").text

    schema = client.get("/config/api-openapi.json").json()
    assert sorted(schema["paths"]) == ["/api/v1/explain", "/api/v1/lookup"]
    assert schema["info"]["title"] == "agent0 API"
    assert schema["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert {"ExplainRequest", "ExplainResponse", "LookupRequest", "LookupResponse", "ErrorResponse"} <= set(
        schema["components"]["schemas"]
    )
    # only what the API uses: nothing from the chat/audio/cv routes
    assert not any(name in schema["components"]["schemas"] for name in ("Body_cv_tailor_cv_tailor_post",))


def test_default_public_docs_are_gone(monkeypatch):
    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"
