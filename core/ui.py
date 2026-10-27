import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from core.agent_routes import agent_router
from core.auth import logout_router, public_router
from core.speech_routes import speech_router
from features.audio.routes import audio_router, audio_static_files
from features.calendar.routes import calendar_router, calendar_static_files

MIN_SESSION_SECRET_LENGTH = 32


def session_secret():
    """SESSION_SECRET from the environment/.env. It signs the login cookie -
    anyone who knows it can forge a logged-in session - so the app refuses to
    start without a long, random one."""
    secret = os.getenv("SESSION_SECRET", "")
    if len(secret) < MIN_SESSION_SECRET_LENGTH:
        raise RuntimeError(
            f"SESSION_SECRET must be set to a random value of at least {MIN_SESSION_SECRET_LENGTH} "
            "characters. Generate one and add it to .env:\n"
            "  python -c \"import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32))\" >> .env"
        )
    return secret


app = FastAPI()

# Feature CSS/JS live under features/<name>/static. They must be
# mounted before the broader /static mount below - Starlette matches mounts
# in registration order, so the more specific prefix has to come first or
# /static would shadow every /static/<feature>/* request.
app.mount("/static/calendar", calendar_static_files(), name="calendar_static")
app.mount("/static/audio", audio_static_files(), name="audio_static")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/favicon", StaticFiles(directory="favicon"), name="favicon")
app.mount("/media", StaticFiles(directory="media"), name="media")
# Generated/saved audio (/audio/<file>) is not mounted here: it is served by
# audio_router (features/audio/routes.py), which requires login.

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret()
)


# Pages are rendered fresh on every request, but without this the browser
# heuristically caches /static CSS/JS - after a UI change it then pairs new
# HTML with a stale stylesheet and the layout breaks. "no-cache" still lets
# it reuse its copy; it just revalidates first (a cheap 304 via the ETag).
@app.middleware("http")
async def revalidate_static_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

# Protected routers first, so their specific paths are matched before the
# catch-all in public_router (included last).
app.include_router(agent_router)
app.include_router(speech_router)
app.include_router(audio_router)
app.include_router(calendar_router)
app.include_router(logout_router)
app.include_router(public_router)


# Exception handler to redirect on 401 (not authenticated)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)
    raise exc
