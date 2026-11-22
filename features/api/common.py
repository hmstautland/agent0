"""Shared by the API routes: the integration key and the one plain model call they make."""
import json

from fastapi import HTTPException
from pydantic import BaseModel

from core import llm

# One on/off flag per endpoint (Config page). Add one for every new endpoint.
EXPLAIN_FLAG = "trading-signals-explain"
LOOKUP_FLAG = "trading-signals-lookup"


class ErrorResponse(BaseModel):
    detail: str


# Documented on every endpoint (the key check, the endpoint flag and the model call can all fail)
ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Missing or wrong API key"},
    403: {"model": ErrorResponse, "description": "This endpoint is switched off on agent0's Config page"},
    502: {"model": ErrorResponse, "description": "The local model is unavailable"},
    503: {"model": ErrorResponse, "description": "AGENT_API_KEY is not set, so the API is disabled"},
}


def as_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def ask(system, user):
    """One chat() call: no tools, no model override (OLLAMA_MODEL), nothing stored."""
    try:
        reply = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], think=False)
    except llm.LLMError:
        raise HTTPException(status_code=502, detail="The local model is unavailable")
    return (reply.get("content") or "").strip()
