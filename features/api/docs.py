"""The OpenAPI schema for outside apps: only /api/v1, and only the models those routes use.

FastAPI's own schema covers the whole app (chat, audio, config...). Swagger UI is
served from the Config page (login required) and fed with this filtered copy.
"""

DESCRIPTION = (
    "Local-model endpoints for the Kush trading-signal app. Authorize with the AGENT_API_KEY from "
    "agent0's .env. Each endpoint has its own on/off switch on the Config page and answers 403 while off. "
    "No tools, no web search, no memory: answers come from the local model plus what you send."
)
PREFIX = "/api/v1/"
SCHEMA_REF = "#/components/schemas/"


def _refs(node, found):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(SCHEMA_REF):
            found.add(ref[len(SCHEMA_REF):])
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _refs(value, found)


def api_schema(app):
    full = app.openapi()
    paths = {path: ops for path, ops in full["paths"].items() if path.startswith(PREFIX)}
    all_schemas = full.get("components", {}).get("schemas", {})

    needed, pending = set(), set()
    _refs(paths, pending)
    while pending:
        name = pending.pop()
        if name in needed or name not in all_schemas:
            continue
        needed.add(name)
        _refs(all_schemas[name], pending)

    components = {"schemas": {name: all_schemas[name] for name in sorted(needed)}}
    if "securitySchemes" in full.get("components", {}):
        components["securitySchemes"] = full["components"]["securitySchemes"]
    return {
        "openapi": full["openapi"],
        "info": {"title": "agent0 API", "version": "1", "description": DESCRIPTION},
        "paths": paths,
        "components": components,
    }
