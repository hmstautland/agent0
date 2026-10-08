import re
import shutil
from features.calendar.calendar import events_in_month, is_calendar_event_list, _parse_datetime
from tools.registry import TOOLS
from tools.notes import parse_note_command, save_note_text
from os import getenv

from agent import run_agent, run_agent_local, stream_agent
from core.permission import PermissionRequired
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from core.speech_to_text import transcribe_audio
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from types import GeneratorType
import json

load_dotenv()
PASSWORD = getenv("APP_LOGIN_PASSWORD")

app = FastAPI()


# The calendar feature's CSS/JS live with its backend logic under
# features/calendar/ rather than in the shared static/ directory - only its
# static/ subfolder is mounted, so calendar.py itself is never served over
# HTTP. Must be mounted before the broader /static mount below - Starlette
# matches mounts in registration order, so the more specific prefix has to
# come first or /static would shadow every /static/calendar/* request.
app.mount("/static/calendar", StaticFiles(directory="features/calendar/static"), name="calendar_static")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/favicon", StaticFiles(directory="favicon"), name="favicon")

templates = Jinja2Templates(directory="templates")


def normalize_stream_value(value):
    if isinstance(value, dict):
        return {str(k): normalize_stream_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_stream_value(v) for v in value]
    if isinstance(value, GeneratorType):
        return [normalize_stream_value(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def serialize_stream_event(event):
    filtered = normalize_stream_value(event)
    return json.dumps(filtered, default=str)


def render_index(request: Request, **context):
    return templates.TemplateResponse(name="index.html", request=request, context=context)


def parse_permission_args(permission_args):
    if not permission_args:
        return None
    try:
        return json.loads(permission_args)
    except Exception:
        return permission_args


def _event_iso(value):
    """Normalize an ics Arrow (or plain datetime) into an ISO string for JSON."""
    if hasattr(value, "naive"):
        try:
            return value.naive.isoformat()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _calendar_target_month(user_input: str):
    """Pick which (year, month) a "show my calendar" chat message means.

    Defaults to the current month; a mentioned day+month (e.g. "17 may")
    opens whichever month contains that date instead.
    """
    target = datetime.now()

    m = re.search(
        r"(\b\d{1,2}\b)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*",
        (user_input or "").lower(),
    )
    if m:
        try:
            target = _parse_datetime(f"{m.group(1)} {m.group(2)}")
        except Exception:
            pass

    return target.year, target.month


def is_calendar_request(user_input: str) -> bool:
    lu = (user_input or "").lower()
    return "calendar" in lu and (
        "show" in lu or "my calendar" in lu or "what's on" in lu or "what is on" in lu
    )


def create_permission_decisions(form):
    permission_decision = form.get("permission_decision")
    permission_action = form.get("permission_action")

    if permission_decision is None or permission_action is None:
        return {}

    decision = permission_decision in ("y", "external")
    return {permission_action: decision}

app.add_middleware(
    SessionMiddleware,
    secret_key="THIS_SECRET"
)

# check if logged in
async def is_logged_in(request: Request):
    if not request.session.get("authenticated") == True:    
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request

public_router = APIRouter()

@public_router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not await is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse(name="index.html",request=request,context={"response":""})

@public_router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(name="login.html", request=request, context={
        "error": None
    })

@public_router.post("/login")
async def login(request: Request, password: str = Form(...)):

    if password == PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(name="login.html", request=request, context={
        "error": "Invalid password"
    })

# Catch-all route for undefined paths
@public_router.get("/{full_path:path}")
async def catch_all(request: Request, full_path: str):
    # If logged in, redirect to home; otherwise to login
    if request.session.get("authenticated") == True:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login", status_code=303)
    
# Private
protected_router = APIRouter(dependencies=[Depends(is_logged_in)])

@protected_router.get("/ask")
async def ask_get(request: Request):
    # Redirect GET requests to / with error message
    return templates.TemplateResponse(name="index.html", request=request, context={
        "response": "",
        "error": "You need to provide 'input' to ask the agent"
    })

@protected_router.get("/calendar/month")
async def calendar_month(year: int = None, month: int = None):
    now = datetime.now()
    year = year or now.year
    month = month if month and 1 <= month <= 12 else now.month

    events = events_in_month(year, month)

    return {
        "year": year,
        "month": month,
        "events": [
            {
                "name": e["name"],
                "start": _event_iso(e["date"]),
                "end": _event_iso(e["end"]),
                "description": e["description"],
            }
            for e in events
        ],
    }

@protected_router.get("/logout")
def logout_page(request: Request):
     return templates.TemplateResponse(name="logout.html", request=request, context={
        "error": None
    })

@protected_router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@protected_router.post("/ask")
async def ask(request: Request):
    try:
        form = await request.form()
        user_input = form.get("input")

        if not user_input:
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": "",
                "error": "You need to provide 'input' to ask the agent"
            })

        note_text = parse_note_command(user_input)
        if note_text is not None:
            note_file = save_note_text(note_text, source="text")
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": f"Note saved to {note_file}",
                "error": None
            })

        # Shortcut: if the user asked to see their calendar, bypass the LLM
        # and open the month-grid calendar view (templates/index.html),
        # which fetches its own data from GET /calendar/month.
        if is_calendar_request(user_input):
            year, month = _calendar_target_month(user_input)
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": "",
                "calendar_month": {"year": year, "month": month},
            })

        permission_decision = form.get("permission_decision")
        permission_action = form.get("permission_action")
        permission_args = parse_permission_args(form.get("permission_args"))
        permission_risk = form.get("permission_risk")

        if permission_decision == "local":
            response = run_agent_local(user_input, permission_action, permission_args, permission_risk)
            
            # Check if response is a fallback dict
            if isinstance(response, dict) and response.get("fallback_to_external"):
                return render_index(request,
                    response=response.get("message"),
                    fallback_permission={
                        "action": response.get("permission_action"),
                        "args": response.get("permission_args"),
                        "risk": response.get("permission_risk"),
                    },
                    input=user_input,
                )
        else:
            permission_decisions = create_permission_decisions(form)

            try:
                response = run_agent(user_input, permission_decisions=permission_decisions)
            except PermissionRequired as pr:
                return render_index(request,
                    response="",
                    permission={
                        "action": pr.action,
                        "args": json.dumps(pr.args),
                        "risk": pr.risk,
                        "reason": pr.reason,
                        "external": TOOLS.get(pr.action, {}).get("external", False),
                    },
                    input=user_input,
                )

        # run_agent() returns a raw calendar event list as-is (rather than
        # text-summarizing it) when the LLM calls read_calendar itself -
        # open the month-grid view on whichever month the first event falls
        # in, instead of rendering the raw list as text.
        calendar_month = None

        if is_calendar_event_list(response):
            first = response[0]
            calendar_month = {"year": first["date"].year, "month": first["date"].month}
            response = ""
        elif isinstance(response, dict) and is_calendar_event_list(response.get("events")):
            first = response["events"][0]
            calendar_month = {"year": first["date"].year, "month": first["date"].month}
            response = ""

        if not isinstance(response, str):
            response = json.dumps(response, indent=2)

        return templates.TemplateResponse(name="index.html", request=request, context={
            "response": str(response),
            "calendar_month": calendar_month,
        })
    
    except Exception as e:
        return templates.TemplateResponse(name="index.html", request=request, context={
            "response": "",
            "error": str(e)
        })

@protected_router.post("/ask_stream")
async def ask_stream(request: Request):
    form = await request.form()
    user_input = form.get("input")

    if not user_input:
        async def error_gen():
            yield json.dumps({"event": "error", "message": "You need to provide 'input' to ask the agent"}) + "\n"
        return StreamingResponse(error_gen(), media_type="application/x-ndjson")

    note_text = parse_note_command(user_input)
    if note_text is not None:
        note_file = save_note_text(note_text, source="text")
        async def note_gen():
            yield json.dumps({"event": "final_response", "response": f"Note saved to {note_file}"}) + "\n"
        return StreamingResponse(note_gen(), media_type="application/x-ndjson")

    if is_calendar_request(user_input):
        year, month = _calendar_target_month(user_input)

        async def calendar_gen():
            yield json.dumps({
                "event": "final_response",
                "response": "",
                "show_calendar": {"year": year, "month": month},
            }) + "\n"
        return StreamingResponse(calendar_gen(), media_type="application/x-ndjson")

    async def event_stream():
        for message in stream_agent(user_input):
            yield serialize_stream_event(message) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@protected_router.post("/speech")
async def speech(file: UploadFile = File(...)):
    temp_path = "local_storage/temp.wav"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text = transcribe_audio(temp_path)
    note_text = parse_note_command(text)
    if note_text is not None:
        note_file = save_note_text(note_text, source="speech")
        return {"text": text, "note_saved": note_file}

    return {"text": text}

@protected_router.get("/speech")
async def speech_get(request: Request):
    # Redirect GET requests to / with error message
    return templates.TemplateResponse(name="index.html", request=request, context={
        "response": "",
        "error": "You need to provide audio input to the speech endpoint"
    })

# Exception handler to redirect on 401 (not authenticated)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=303)
    raise exc

app.include_router(protected_router)
app.include_router(public_router)