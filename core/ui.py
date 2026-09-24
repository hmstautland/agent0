from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from core.agent_routes import agent_router
from core.auth import logout_router, public_router
from core.speech_routes import speech_router

load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/favicon", StaticFiles(directory="favicon"), name="favicon")
app.mount("/media", StaticFiles(directory="media"), name="media")

app.add_middleware(
    SessionMiddleware,
    secret_key="THIS_SECRET"
)

# Protected routers first, so their specific paths are matched before the
# catch-all in public_router (included last).
app.include_router(agent_router)
app.include_router(speech_router)
app.include_router(logout_router)
app.include_router(public_router)


# Exception handler to redirect on 401 (not authenticated)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)
    raise exc
