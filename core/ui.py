import shutil
from tools.calendar import read_calendar, _parse_datetime
from tools.registry import TOOLS
from os import getenv

from agent import run_agent, run_agent_local
from core.permission import PermissionRequired
from fastapi import FastAPI, Request, Form, UploadFile, File, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from core.speech_to_text import transcribe_audio
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import json

load_dotenv()
PASSWORD = getenv("APP_LOGIN_PASSWORD")

app = FastAPI()

# Login - instead of checking each page, group them
# async def verify_logged_in():
#     # Replace with your actual logic (session check, JWT, etc.)
#     is_logged_in = False 
#     if not is_logged_in:
#         raise HTTPException(status_code=401, detail="Not logged in")


# public_router = APIRouter()

app.add_middleware(
    SessionMiddleware,
    secret_key="THIS_SECRET"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# check if logged in
def is_logged_in(request: Request):
    return request.session.get("authenticated") == True

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse(name="index.html",request=request,context={"response":""})


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(name="login.html", request=request, context={
        "error": None
    })

@app.post("/login")
async def login(request: Request, password: str = Form(...)):

    if password == PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(name="login.html", request=request, context={
        "error": "Invalid password"
    })

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.post("/ask")
async def ask(request: Request):
    try:
        form = await request.form()
        user_input = form.get("input")

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
        permission_args = form.get("permission_args")
        permission_risk = form.get("permission_risk")

        if permission_args:
            try:
                permission_args = json.loads(permission_args)
            except Exception:
                pass

        permission_decisions = None

        if permission_decision == "local":
            response = run_agent_local(user_input, permission_action, permission_args, permission_risk)
            
            # Check if response is a fallback dict
            if isinstance(response, dict) and response.get("fallback_to_external"):
                return templates.TemplateResponse(name="index.html", request=request, context={
                    "response": response.get("message"),
                    "fallback_permission": {
                        "action": response.get("permission_action"),
                        "args": response.get("permission_args"),
                        "risk": response.get("permission_risk"),
                    },
                    "input": user_input,
                })
        else:
            # Build a decisions map for web flow. Use empty dict to signal web UI
            # so request_permission raises PermissionRequired instead of prompting.
            permission_decisions = {}
            if permission_decision is not None and permission_action is not None:
                decision = permission_decision in ("y", "external")
                permission_decisions = {permission_action: decision}

            try:
                response = run_agent(user_input, permission_decisions=permission_decisions)
            except PermissionRequired as pr:
                # Render UI asking for permission approval
                return templates.TemplateResponse(name="index.html", request=request, context={
                    "response": "",
                    "permission": {
                        "action": pr.action,
                        "args": json.dumps(pr.args),
                        "risk": pr.risk,
                        "reason": pr.reason,
                        "external": TOOLS.get(pr.action, {}).get("external", False),
                    },
                    "input": user_input,
                })

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
    
@app.post("/speech")
async def speech(file: UploadFile = File(...)):
    temp_path = "local_storage/temp.wav"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text = transcribe_audio(temp_path)

    return {"text": text}