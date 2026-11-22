"""HTTP API for outside apps (the Kush trading-signal app). Bearer-key auth on the
whole router; each endpoint has its own on/off flag (Config page), set in its own
route.py with require_integration(<flag>).

Each endpoint lives in its own folder (explain/route.py, lookup/route.py) and is
mounted here. They are plain calls to the local model: no tools, no web search,
no permission grants, no conversation memory, no model override (OLLAMA_MODEL).
A new endpoint = a new folder with a route.py (with its own flag in common.py),
included below.
"""
from fastapi import APIRouter, Depends

from features.api.auth import require_api_key
from features.api.explain.route import router as explain_router
from features.api.lookup.route import router as lookup_router

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(explain_router)
api_router.include_router(lookup_router)
