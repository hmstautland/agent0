import os
import requests

# Older setting (the /api/generate endpoint) - still honoured, so an existing
# OLLAMA_URL pointing at another host keeps working for the chat URL below.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# The agent loop talks to /api/chat on the same local server: it carries the
# conversation as messages and supports Ollama's built-in tool calling.
OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", OLLAMA_URL.rsplit("/api/", 1)[0] + "/api/chat")

# Light model for direct answers and the local-first check. qwen3:4b is both
# faster than mistral:7b on CPU (34 vs 24 tok/s generation, 206 vs 100 tok/s
# prompt) and, unlike mistral, it admits when a request needs the file tools
# instead of inventing an answer about code it never read.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

# Model used once the request escalates to the tool loop. Reading and editing
# files needs far more instruction-following than answering a question, and a
# 4B model cannot drive a multi-step edit reliably.
OLLAMA_CODE_MODEL = os.getenv("OLLAMA_CODE_MODEL", "qwen3-coder:30b")

# Ollama defaults to a 4096 token context. Reading a single template can exceed
# that, and the overflow is silently truncated - the model then loses the
# instructions and replies with prose or invented tool names.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))

# Reading a large file into the prompt takes a while on CPU-only inference
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))


class LLMError(RuntimeError):
    """Ollama could not be reached, or did not return a usable answer."""


def chat(messages, model=None, tools=None, format=None, think=None):
    """One /api/chat call. Returns the assistant message dict.

    tools is a list of JSON-schema function definitions (Ollama's built-in
    tool calling); the calls the model makes come back in
    message["tool_calls"]. format is a JSON schema the reply must follow
    (structured outputs). Everything runs on the local Ollama server.
    """
    payload = {
        "model": model or OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX},
    }
    if tools:
        payload["tools"] = tools
    if format is not None:
        payload["format"] = format
    if think is not None:
        payload["think"] = think

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
