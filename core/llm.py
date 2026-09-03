import os
import json
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")


def _query_llm_stream(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
    }

    response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120)
    response.raise_for_status()

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue

        text = chunk.get("response")
        if text is not None:
            yield text


def query_llm(prompt, stream=False):
    if stream:
        return _query_llm_stream(prompt)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()

    body = response.json()
    if isinstance(body, dict):
        return body.get("response") or body.get("text") or json.dumps(body)
    return str(body)
