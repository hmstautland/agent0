import pytest

import core.permission as permission
from core.ui import MIN_SESSION_SECRET_LENGTH, session_secret
from tools.registry import TOOLS


def test_external_tools_ask_until_granted_even_with_low_risk():
    assert permission.needs_approval("get_news", TOOLS["get_news"]) is True
    assert permission.needs_approval("get_news", TOOLS["get_news"], granted={"get_news"}) is False
    assert permission.needs_approval("search_web", TOOLS["search_web"], granted={"get_news"}) is True


def test_rules_then_risk_decide_for_other_tools(monkeypatch):
    monkeypatch.setattr(permission, "RULES", {"read_files": "auto", "play_audio_file": "ask"})

    assert permission.needs_approval("read_files", TOOLS["read_files"]) is False
    assert permission.needs_approval("play_audio_file", TOOLS["play_audio_file"]) is True
    assert permission.needs_approval("save_note", TOOLS["save_note"]) is False
    assert permission.needs_approval("write_file", TOOLS["write_file"]) is True


def test_every_registered_tool_has_a_parameter_schema():
    for name, tool in TOOLS.items():
        schema = tool["parameters"]
        assert schema["type"] == "object", name
        assert set(schema["required"]) <= set(schema["properties"]), name


def test_app_refuses_a_missing_or_short_session_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        session_secret()

    monkeypatch.setenv("SESSION_SECRET", "x" * (MIN_SESSION_SECRET_LENGTH - 1))
    with pytest.raises(RuntimeError):
        session_secret()

    monkeypatch.setenv("SESSION_SECRET", "x" * MIN_SESSION_SECRET_LENGTH)
    assert session_secret() == "x" * MIN_SESSION_SECRET_LENGTH
