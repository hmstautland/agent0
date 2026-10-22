import json
import os

import requests

from core import cancel

# Older setting (the /api/generate endpoint) - still honoured, so an existing
# OLLAMA_URL pointing at another host keeps working for the chat URL below.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# The agent loop talks to /api/chat on the same local server: it carries the
# conversation as messages and supports Ollama's built-in tool calling.
OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/chat")

# General model: direct answers, the local-first check, and the tool loop for
# tasks that are not about code (web search, calendar, notes, ...). A
# mixture-of-experts model with ~3B active parameters, so it generates about
# as fast as the dense qwen3:8b it replaced while knowing far more.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.6:35b")

# Model for the tool loop when the task is about code or the project's files.
# Reading and editing files needs far more instruction-following than
# answering a question, and a small model cannot drive a multi-step edit.
OLLAMA_CODE_MODEL = os.getenv("OLLAMA_CODE_MODEL", "qwen3-coder:30b")

# Ollama defaults to a 4096 token context, and overflow is silently truncated -
# the model then loses the instructions and replies with prose or invented tool
# names. Both models can run the tool loop, which accumulates file reads and
# search results, so both get a large window. The window is per model, not per
# call: Ollama reloads a model whenever num_ctx changes.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
OLLAMA_CODE_NUM_CTX = int(os.getenv("OLLAMA_CODE_NUM_CTX", "32768"))

# Reading a large file into the prompt can take a while, especially without a GPU
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))


class LLMError(RuntimeError):
    """Ollama could not be reached, or did not return a usable answer."""


def _payload(messages, model, tools, format, think, stream):
    model = model or OLLAMA_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "options": {"num_ctx": OLLAMA_CODE_NUM_CTX if model == OLLAMA_CODE_MODEL else OLLAMA_NUM_CTX},
    }
    if tools:
        payload["tools"] = tools
    if format is not None:
        payload["format"] = format
    if think is not None:
        payload["think"] = think
    return payload


def chat(messages, model=None, tools=None, format=None, think=None):
    """One /api/chat call. Returns the assistant message dict.

    tools is a list of JSON-schema function definitions (Ollama's built-in
    tool calling); the calls the model makes come back in
    message["tool_calls"]. format is a JSON schema the reply must follow
    (structured outputs). Everything runs on the local Ollama server.
    """
    payload = _payload(messages, model, tools, format, think, stream=False)

    try:
        response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
        body = response.json()
    except requests.HTTPError as e:
        raise LLMError(f"Ollama returned an error ({e.response.status_code}): {e.response.text[:300]}") from e
    except requests.RequestException as e:
        raise LLMError(f"Could not reach Ollama at {OLLAMA_CHAT_URL}. Is `ollama serve` running? ({e})") from e
    except ValueError as e:
        raise LLMError(f"Ollama returned a reply that is not JSON: {e}") from e

    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        raise LLMError(f"Ollama returned no message: {str(body)[:300]}")

    return message


def chat_stream(messages, model=None, tools=None, format=None, think=None):
    """Like chat(), but streamed: a generator for `message = yield from chat_stream(...)`.

    Yields {"event": "llm_delta", "kind": "thinking" | "content", "text": ...}
    as Ollama produces text, so the web UI can show the model working. Returns
    the same assembled assistant message dict chat() would.
    """
    payload = _payload(messages, model, tools, format, think, stream=True)
    content, thinking, tool_calls = [], [], []

    try:
        with requests.post(OLLAMA_CHAT_URL, json=payload, timeout=OLLAMA_TIMEOUT, stream=True) as response:
            cancel.attach(response)  # a stop (core/cancel.py) can cut this connection off
            try:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if not isinstance(chunk, dict):
                        raise LLMError(f"Ollama returned an unexpected chunk: {str(chunk)[:300]}")
                    if chunk.get("error"):
                        raise LLMError(f"Ollama returned an error: {str(chunk['error'])[:300]}")

                    message = chunk.get("message") or {}
                    for kind, parts in (("thinking", thinking), ("content", content)):
                        text = message.get(kind)
                        if text:
                            parts.append(text)
                            yield {"event": "llm_delta", "kind": kind, "text": text}
                    tool_calls.extend(message.get("tool_calls") or [])

                    if chunk.get("done"):
                        break
            finally:
                cancel.detach(response)
    except requests.HTTPError as e:
        raise LLMError(f"Ollama returned an error ({e.response.status_code}): {e.response.text[:300]}") from e
    except requests.RequestException as e:
        raise LLMError(f"Could not reach Ollama at {OLLAMA_CHAT_URL}. Is `ollama serve` running? ({e})") from e
    except ValueError as e:
        raise LLMError(f"Ollama returned a reply that is not JSON: {e}") from e

    message = {"role": "assistant", "content": "".join(content)}
    if thinking:
        message["thinking"] = "".join(thinking)
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message
