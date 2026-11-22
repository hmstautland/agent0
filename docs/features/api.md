# HTTP API (Kush trading-signal app)

A small HTTP API that lets the Kush trading-signal app call agent0 for two things: **explain** a signal in natural language, and **look up** answers for its search bar. Everything runs on the local Ollama model.

## Using it

1. Add a key to `.env`: `AGENT_API_KEY=<random value>` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`), and restart.
2. Open **Config** (top-left link) and switch on *Explain* and/or *Lookup*. Each endpoint has its own switch and is off until you turn it on.
3. Call the API with `Authorization: Bearer <key>`:

```
POST /api/v1/explain
{"subject": "AAPL buy signal",
 "facts": {"RSI": 32.1, "SMA20": 185.40, "SMA50": 182.10, "risk_checks": "passed"},
 "style": "short"}                      # "short" (default) or "detailed"
-> {"explanation": "...", "model": "qwen3.6:35b"}

POST /api/v1/lookup
{"query": "which signal is strongest between AAPL and MSFT?",
 "context": {"portfolio": ["AAPL", "NVDA"], "signals": {...}}}   # context is optional
-> {"answer": "...", "model": "qwen3.6:35b"}
```

`facts` and `context` can be a string, an object or a list. agent0 doesn't hold the app's portfolio, so for portfolio questions the app sends it in `context`.

Client sketch for the app (fall back to the old template if the call fails):

```python
def explain(signal_text, facts):
    try:
        r = requests.post(f"{AGENT0}/api/v1/explain", json={"subject": signal_text, "facts": facts},
                          headers={"Authorization": f"Bearer {KEY}"}, timeout=120)
        r.raise_for_status()
        return r.json()["explanation"]
    except requests.RequestException:
        return signal_text  # the fixed template string
```

| Status | Meaning |
| --- | --- |
| 401 | Missing or wrong key (JSON, not a login redirect) |
| 403 | Key is right but that endpoint is switched off on the Config page |
| 422 | Bad body, or unknown `style` |
| 502 | The local model is unavailable |
| 503 | `AGENT_API_KEY` is not set |

## How it works

`features/api/` holds a router under `/api/v1` (`routes.py`); each endpoint is its own folder with a `route.py` (`explain/`, `lookup/`), and shared code is in `common.py`. Every request checks the key first (`secrets.compare_digest`), then the endpoint's own flag (`trading-signals-explain` or `trading-signals-lookup`, constants in `common.py`) from the database (`storage/integrations.py`), so switching one off or on applies immediately and doesn't affect the other. Each endpoint's `route.py` sets its flag with `require_integration(...)`; a test walks the published `/api/v1` routes and fails if one is reachable with all flags off.

Both endpoints make one plain `core.llm.chat` call with their own system prompt. They never go through `agent.py`, the tool registry or `needs_approval`, and they store nothing in conversation memory.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `AGENT_API_KEY` | unset | The Bearer key. Unset means the API answers 503. |
| `OLLAMA_MODEL` | `qwen3.6:35b` | The model both endpoints use (no separate setting). |

## Limits

- No tools and no web search: answers come from the model's own knowledge plus what the app sends, so facts like a company's sector can be out of date.
- Calls are slow on the 35B model (use a long client timeout) and block one Ollama request each.
- One shared key for all endpoints; there is no per-app key or rate limit.
- The earlier combined `trading-signals` flag is no longer read; switch Explain and Lookup on separately.
