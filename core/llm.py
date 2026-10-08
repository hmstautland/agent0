import os
import json
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

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


def query_llm(prompt, model=None):
    payload = {
        "model": model or OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX},
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    response.raise_for_status()

    body = response.json()
    if isinstance(body, dict):
        return body.get("response") or body.get("text") or json.dumps(body)
    return str(body)
