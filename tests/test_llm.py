import pytest

import core.llm as llm


class FakeResponse:
    def __init__(self, body=None):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_chat_sends_tools_to_the_local_chat_endpoint_and_returns_the_message(monkeypatch):
    sent = {}
    message = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search_files", "arguments": {"keyword": "x"}}}]}

    def fake_post(url, json=None, **kwargs):
        sent.update(url=url, **json)
        return FakeResponse({"message": message})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    tools = [{"type": "function", "function": {"name": "search_files"}}]

    assert llm.chat([{"role": "user", "content": "hi"}], tools=tools) == message
    assert sent["url"] == llm.OLLAMA_CHAT_URL
    assert sent["tools"] == tools and sent["stream"] is False


def test_chat_turns_connection_failures_into_llm_error(monkeypatch):
    def refuse(*args, **kwargs):
        raise llm.requests.ConnectionError("refused")

    monkeypatch.setattr(llm.requests, "post", refuse)

    with pytest.raises(llm.LLMError, match="Could not reach Ollama"):
        llm.chat([{"role": "user", "content": "hi"}])
