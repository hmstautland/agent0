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
from features.audio.text_to_speech import AUDIO_DIR
from features.calendar.routes import calendar_router, calendar_static_files

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
# Generated/saved audio files - AUDIO_DIR is created at import time in
# features/audio/text_to_speech.py
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

app.add_middleware(
    SessionMiddleware,
    secret_key="THIS_SECRET"
)

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
