import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

def query_llm(prompt):
    res = requests.post(OLLAMA_URL, json={
        "model": "mistral:7b",
        "prompt": prompt,
        "stream": False
    })

    return res.json()["response"]