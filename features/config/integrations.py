"""The integrations that can be switched on or off on the Config page.

Adding one is adding an entry here; its flag lives in storage/integrations.py
and is off until someone turns it on. API endpoints each have their own flag
(constants in features/api/common.py), so each one is its own card.
"""
from features.api.common import EXPLAIN_FLAG, LOOKUP_FLAG

NO_MODEL_SETTING = (
    "No new model setting. The endpoint uses the existing OLLAMA_MODEL (core/llm.py:46, "
    "already qwen3.6:35b) by not passing a model to chat(). No OLLAMA_SMALL_MODEL, no extra "
    "num_ctx setting, nothing changes for the rest of the app."
)
NO_TOOLS = (
    "Lookup uses none of agent0's tools, including web search. Answers come from the model's "
    "own knowledge plus whatever the caller sends."
)
NO_GRANTS = (
    "No permission grants anywhere, hard-coded or sent by the caller. The API never goes "
    "through needs_approval, granted, or parked runs."
)
NEEDS_KEY = "AGENT_API_KEY in .env (the app sends it as a Bearer token)"

INTEGRATIONS = [
    {
        "key": EXPLAIN_FLAG,
        "name": "Trading signals (Kush app): Explain",
        "description": (
            "Lets the Kush trading-signal app ask agent0 to explain a signal. It replaces the "
            "app's fixed explain() template string with a natural-language explanation: why the "
            "signal matters, what the price action suggests, and whether it is a strong or weak "
            "setup. The answer comes from the local model plus the facts the app sends - no "
            "agent0 tools, no web search. While this is off, the app gets 403 from this endpoint."
        ),
        "endpoints": ["POST /api/v1/explain"],
        "needs": NEEDS_KEY,
        "decisions": [NO_MODEL_SETTING, NO_GRANTS],
    },
    {
        "key": LOOKUP_FLAG,
        "name": "Trading signals (Kush app): Lookup",
        "description": (
            "Powers the Kush app's search bar with agent0 as a lookup, for questions like "
            "\"which signal is strongest based on my current portfolio between these 2 stocks?\" "
            "or \"what sector is this stock?\". Answers come from the local model's own knowledge "
            "plus whatever the app sends (such as its portfolio) - no agent0 tools, no web "
            "search. While this is off, the app gets 403 from this endpoint."
        ),
        "endpoints": ["POST /api/v1/lookup"],
        "needs": NEEDS_KEY,
        "decisions": [NO_MODEL_SETTING, NO_TOOLS, NO_GRANTS],
    },
]


def get(key):
    return next((i for i in INTEGRATIONS if i["key"] == key), None)
