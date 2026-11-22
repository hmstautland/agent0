"""The Config page: a dashboard where integrations are switched on and off.
Login required. Static assets (features/config/static) are served at /static/config."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.auth import is_logged_in
from core.templates import templates
from features.api.docs import api_schema
from features.config import integrations
from storage import integrations as flags

STATIC_DIR = Path(__file__).resolve().parent / "static"

config_router = APIRouter(dependencies=[Depends(is_logged_in)])


@config_router.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    cards = [
        {**item, "enabled": flags.is_enabled(item["key"])}
        for item in integrations.INTEGRATIONS
    ]
    return templates.TemplateResponse(
        name="config/config.html",
        request=request,
        context={
            "integrations": cards,
            # Only whether it is set - the key itself never goes to the page
            "api_key_set": bool(os.getenv("AGENT_API_KEY")),
        },
    )


@config_router.post("/config/integrations/{key}")
def set_integration(key: str, enabled: str = Form("0")):
    if integrations.get(key) is None:
        raise HTTPException(status_code=404, detail="Unknown integration")
    flags.set_enabled(key, enabled == "1")
    return RedirectResponse(url="/config", status_code=303)


# API docs for outside apps: Swagger UI plus the /api/v1-only schema, behind login.
# (Swagger UI's own JS/CSS load from a CDN in the browser; the API itself needs no internet.)
@config_router.get("/config/api-openapi.json", include_in_schema=False)
def api_openapi(request: Request):
    return api_schema(request.app)


@config_router.get("/config/api-docs", include_in_schema=False)
def api_docs():
    return get_swagger_ui_html(openapi_url="/config/api-openapi.json", title="agent0 API")


def config_static_files():
    return StaticFiles(directory=str(STATIC_DIR))
