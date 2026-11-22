"""Auth for the HTTP API other apps use: a Bearer key, then the integration's on/off flag.

The key is checked first, so a caller without it learns nothing about whether
the integration is switched on.
"""
import os
import secrets

from fastapi import Depends, HTTPException, Request

from storage import integrations


def require_api_key(request: Request):
    expected = os.getenv("AGENT_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="API disabled: AGENT_API_KEY is not set")
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing API key", headers={"WWW-Authenticate": "Bearer"})


def require_integration(key):
    """Dependency: 403 unless the integration is switched on (read on every request)."""

    def check(_: None = Depends(require_api_key)):
        if not integrations.is_enabled(key):
            raise HTTPException(status_code=403, detail="integration disabled")

    return check
