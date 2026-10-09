import json

import core.llm as llm


class FakeResponse:
    def __init__(self, body=None, lines=()):
        self._body = body
        self._lines = lines

    def raise_for_status(self):
        pass

    def json(self):
        return self._body

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)


def test_query_llm_returns_the_response_text_by_default(monkeypatch):
    sent = {}

    def fake_post(url, json=None, **kwargs):
        sent.update(json)
        return FakeResponse({"response": "hello"})

    monkeypatch.setattr(llm.requests, "post", fake_post)

    assert llm.query_llm("hi") == "hello"
    assert sent["stream"] is False


def test_query_llm_stream_yields_chunks(monkeypatch):
    lines = [json.dumps({"response": "he"}), "", json.dumps({"response": "llo"})]
    sent = {}

    def fake_post(url, json=None, **kwargs):
        sent.update(json)
        return FakeResponse(lines=lines)

    monkeypatch.setattr(llm.requests, "post", fake_post)

    assert list(llm.query_llm("hi", stream=True)) == ["he", "llo"]
    assert sent["stream"] is True
