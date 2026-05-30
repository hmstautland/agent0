import shutil
from tools.calendar import read_calendar, _parse_datetime
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

        # # move calendar logic out to calendar.py and import here
        # Shortcut: if user asked to see their calendar, bypass LLM and show structured events
        lu = (user_input or "").lower()
        if "calendar" in lu and ("show" in lu or "my calendar" in lu or "what's on" in lu or "what is on" in lu):
            events = read_calendar()

            # If asking for today, filter to today's date
            if "today" in lu:
                today = datetime.now().date()
                def _event_date(ev):
                    d = ev.get("date")
                    if hasattr(d, "date") and callable(d.date):
                        return d.date()
                    if isinstance(d, datetime):
                        return d.date()
                    if hasattr(d, "naive"):
                        try:
                            return d.naive.date()
                        except Exception:
                            pass
                    return None

                events = [e for e in events if _event_date(e) == today]

            # If asking for a specific day like 'may 17', try to parse and filter
            import re
            m = re.search(r"(\b\d{1,2}\b)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", lu)
            if m:
                day = int(m.group(1))
                month_str = m.group(2)
                try:
                    dt = _parse_datetime(f"{day} {month_str}")
                    def _event_date2(ev):
                        d = ev.get("date")
                        if hasattr(d, "date") and callable(d.date):
                            return d.date()
                        if isinstance(d, datetime):
                            return d.date()
                        if hasattr(d, "naive"):
                            try:
                                return d.naive.date()
                            except Exception:
                                pass
                        return None

                    events = [e for e in events if _event_date2(e) == dt.date()]
                except Exception:
                    pass

            # Normalize date objects to datetimes for the template
            def _to_dt(x):
                if hasattr(x, "naive"):
                    try:
                        return x.naive
                    except Exception:
                        pass
                if hasattr(x, "datetime"):
                    try:
                        return x.datetime
                    except Exception:
                        pass
                return x

            for e in events:
                if "date" in e:
                    e["date"] = _to_dt(e["date"])
                if "end" in e:
                    e["end"] = _to_dt(e["end"])

            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": "",
                "calendar_data": events,
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

        calendar_data = None

        if isinstance(response, list) and response:
            first = response[0]
            if isinstance(first, dict) and "date" in first and "end" in first:
                calendar_data = response
                response = ""

        if isinstance(response, dict) and response.get("events"):
            calendar_data = response["events"]
            response = ""

        if not isinstance(response, str):
            response = json.dumps(response, indent=2)
        # Normalize calendar_data dates if present
        def _to_dt(x):
            if hasattr(x, "naive"):
                try:
                    return x.naive
                except Exception:
                    pass
            if hasattr(x, "datetime"):
                try:
                    return x.datetime
                except Exception:
                    pass
            return x

        if calendar_data:
            for e in calendar_data:
                if "date" in e:
                    e["date"] = _to_dt(e["date"])
                if "end" in e:
                    e["end"] = _to_dt(e["end"])

        return templates.TemplateResponse(name="index.html", request=request, context={    
            "response": str(response),
            "calendar_data": calendar_data
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

    lu = (user_input or "").lower()
    if "calendar" in lu and ("show" in lu or "my calendar" in lu or "what's on" in lu or "what is on" in lu):
        events = read_calendar()
        if "today" in lu:
            today = datetime.now().date()
            def _event_date(ev):
                d = ev.get("date")
                if hasattr(d, "date") and callable(d.date):
                    return d.date()
                if isinstance(d, datetime):
                    return d.date()
                if hasattr(d, "naive"):
                    try:
                        return d.naive.date()
                    except Exception:
                        pass
                return None

            events = [e for e in events if _event_date(e) == today]

        import re
        m = re.search(r"(\b\d{1,2}\b)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", lu)
        if m:
            day = int(m.group(1))
            month_str = m.group(2)
            try:
                dt = _parse_datetime(f"{day} {month_str}")
                def _event_date2(ev):
                    d = ev.get("date")
                    if hasattr(d, "date") and callable(d.date):
                        return d.date()
                    if isinstance(d, datetime):
                        return d.date()
                    if hasattr(d, "naive"):
                        try:
                            return d.naive.date()
                        except Exception:
                            pass
                    return None

                events = [e for e in events if _event_date2(e) == dt.date()]
            except Exception:
                pass

        def _to_dt(x):
            if hasattr(x, "naive"):
                try:
                    return x.naive
                except Exception:
                    pass
            if hasattr(x, "datetime"):
                try:
                    return x.datetime
                except Exception:
                    pass
            return x

        for e in events:
            if "date" in e:
                e["date"] = _to_dt(e["date"])
            if "end" in e:
                e["end"] = _to_dt(e["end"])

        async def calendar_gen():
            yield json.dumps({"event": "final_response", "response": "Calendar query completed.", "calendar_data": events}) + "\n"
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