import os
import json
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")


def query_llm(prompt, stream=False):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": stream,
    }

    if stream:
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
        return

    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()

    body = response.json()
    if isinstance(body, dict):
        return body.get("response") or body.get("text") or json.dumps(body)
    return str(body)
