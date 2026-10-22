import json

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


class FakeStreamResponse:
    def __init__(self, chunks):
        self._lines = [json.dumps(c).encode() for c in chunks]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)


def drain(gen):
    """Collect a chat_stream generator's yielded events and its return value."""
    events = []
    while True:
        try:
            events.append(next(gen))
        except StopIteration as stop:
            return events, stop.value


def test_chat_stream_yields_deltas_and_returns_the_assembled_message(monkeypatch):
    sent = {}
    call = {"function": {"name": "read_file", "arguments": {"path": "a.txt"}}}
    chunks = [
        {"message": {"role": "assistant", "content": "", "thinking": "Let me "}},
        {"message": {"role": "assistant", "content": "", "thinking": "check."}},
        {"message": {"role": "assistant", "content": "Reading", "tool_calls": [call]}},
        {"message": {"role": "assistant", "content": " it."}, "done": True},
    ]

    def fake_post(url, json=None, **kwargs):
        sent.update(json, stream_kw=kwargs.get("stream"))
        return FakeStreamResponse(chunks)

    monkeypatch.setattr(llm.requests, "post", fake_post)

    events, message = drain(llm.chat_stream([{"role": "user", "content": "hi"}]))

    assert sent["stream"] is True and sent["stream_kw"] is True
    assert [(e["kind"], e["text"]) for e in events] == [
        ("thinking", "Let me "), ("thinking", "check."), ("content", "Reading"), ("content", " it."),
    ]
    assert message == {"role": "assistant", "content": "Reading it.", "thinking": "Let me check.", "tool_calls": [call]}


def test_chat_stream_turns_an_error_chunk_into_llm_error(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeStreamResponse([{"error": "model not found"}]))

    with pytest.raises(llm.LLMError, match="model not found"):
        drain(llm.chat_stream([{"role": "user", "content": "hi"}]))


def test_payload_uses_the_larger_context_only_for_the_code_model():
    def num_ctx(model):
        return llm._payload([], model, None, None, None, False)["options"]["num_ctx"]

    assert num_ctx(llm.OLLAMA_CODE_MODEL) == llm.OLLAMA_CODE_NUM_CTX
    assert num_ctx(llm.OLLAMA_MODEL) == llm.OLLAMA_NUM_CTX
    assert num_ctx(None) == llm.OLLAMA_NUM_CTX
