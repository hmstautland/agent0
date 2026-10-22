import json
import re
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

import core.cancel as cancel
import core.conversations as conversations
from agent import resume_agent, stream_agent
from core.auth import is_logged_in
from core.logger import log_event
from core.runs import take
from core.streaming import serialize_stream_event
from core.templates import templates
from features.calendar.calendar import (
    calendar_target_month,
    create_event_from_command,
    is_calendar_request,
)
from features.audio.player import describe_play_result, parse_play_command, play_audio_file
from tools.notes import parse_note_command, save_note_text
from tools.registry import TOOLS

agent_router = APIRouter(dependencies=[Depends(is_logged_in)])


def render_index(request: Request, **context):
    return templates.TemplateResponse(name="index.html", request=request, context=context)


def session_owner(request: Request):
    """Id of this login session - a parked run can only be resumed by the session that started it."""
    owner = request.session.get("sid")
    if not owner:
        owner = request.session["sid"] = secrets.token_urlsafe(16)
    return owner


def session_grants(request: Request):
    """External tools the user approved during this login session (cleared on logout)."""
    return set(request.session.get("external_grants", []))


def grant_external(request: Request, action):
    # Must happen in the handler, before a StreamingResponse starts: the
    # session cookie is written with the response headers.
    request.session["external_grants"] = sorted(session_grants(request) | {action})


def session_conversation(request: Request, new=False):
    """This login session's conversation id (core/conversations.py). Logging out starts a new one.

    Like grant_external, call it in the handler - the session cookie is
    written with the response headers.
    """
    conversation_id = request.session.get("conversation_id")
    if new or not conversation_id:
        conversation_id = request.session["conversation_id"] = conversations.new_conversation()
    return conversation_id


def resume_events(request: Request, run_id, approved):
    """Events for continuing a parked run with the user's decision."""
    run = take(run_id, owner=session_owner(request))
    if run is None:
        return iter([{
            "event": "error",
            "message": "This approval is no longer valid: it was already answered, it expired, "
                       "or the server restarted. Send your request again.",
        }])

    if approved and TOOLS[run.pending["name"]].get("external"):
        grant_external(request, run.pending["name"])

    return resume_agent(run, approved)


def agent_events(request: Request, user_input):
    """Events answering user_input: a shortcut's, or the agent's. Either way stored in the session's conversation."""
    conversation_id = session_conversation(request)
    shortcut = shortcut_events(user_input)
    if shortcut is not None:
        return conversations.record(shortcut, conversation_id, user_input)
    return stream_agent(
        user_input, owner=session_owner(request), granted=session_grants(request), conversation_id=conversation_id,
    )


def shortcut_events(user_input):
    """Requests answered without the LLM, as a list of events - or None.

    The local model isn't reliable at recognizing these need a specific tool
    rather than answering "I can't do that" directly.
    """
    shortcut = shortcut_text_response(user_input)
    if shortcut is not None:
        return [{"event": "final_response", "response": shortcut}]

    # "add a meeting ..." - create it and open the calendar on the new
    # event's month (or reply asking to restate the date/time)
    calendar_result = create_event_from_command(user_input)
    if calendar_result is not None:
        return [{"event": "final_response", **calendar_result}]

    # "play ..." - hand the web UI a concrete file to play, or candidates to
    # choose between
    audio_result = audio_play_result(user_input)
    if audio_result is not None:
        return [{"event": "final_response", "response": describe_play_result(audio_result), "audio": audio_result}]

    # Asked to see the calendar: open the month-grid calendar
    # (features/calendar), which fetches its own data from GET /calendar/month.
    if is_calendar_request(user_input):
        year, month = calendar_target_month(user_input)
        return [{"event": "final_response", "response": "", "show_calendar": {"year": year, "month": month}}]

    return None


def shortcut_text_response(user_input):
    """Handle note-taking requests that bypass the LLM.

    The local model isn't reliable at recognizing these need a specific tool
    rather than answering "I can't do that" directly. Returns response text,
    or None if user_input isn't one.
    """
    note_text = parse_note_command(user_input)
    if note_text is not None:
        note_file = save_note_text(note_text, source="text")
        return f"Note saved to {note_file}"

    return None


def audio_play_result(user_input):
    """Handle "play ..." requests directly - same reasoning as
    shortcut_text_response: the local model isn't reliable at recognizing
    this needs the audio tool. Returns the play_audio_file() result dict, or
    None if user_input isn't a play request.
    """
    play_args = parse_play_command(user_input)
    if play_args is None:
        return None

    return play_audio_file(**play_args)


def page_context(events):
    """Drain agent events into the index.html context for the plain /ask page."""
    context = {"response": ""}

    for event in events:
        etype = event.get("event")

        if etype == "final_response":
            context["response"] = event.get("response") or ""
            if event.get("show_calendar"):
                context["calendar_month"] = event["show_calendar"]
            if event.get("audio"):
                context["audio_data"] = event["audio"]
        elif etype == "error":
            context["error"] = event.get("message")
        elif etype == "permission_required":
            context["permission"] = {
                "run_id": event["run_id"],
                "action": event["action"],
                "args": json.dumps(event["args"], indent=2),
                "risk": event["risk"],
                "external": event["external"],
                "reason": event["reason"],
            }

    return context


REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Tools that only look; the stop reply lists the others as "already done"
READ_ONLY_TOOLS = {"read_files", "search_files", "get_project_structure", "list_notes", "search_history", "verify_app"}


def ndjson_response(events, request_id=None, owner=None):
    """Stream events as NDJSON. With a request_id the request can be stopped (POST /ask_stream/stop)."""
    if request_id:
        events = cancel.scoped(events, cancel.begin(request_id, owner))

    # A plain (sync) generator: Starlette iterates it in a worker thread, so
    # slow LLM calls don't block the event loop.
    def body():
        try:
            for event in events:
                yield serialize_stream_event(event) + "\n"
        except Exception as e:
            log_event({"type": "stream_error", "error": repr(e)})
            yield serialize_stream_event({"event": "error", "message": f"Something went wrong: {e}"}) + "\n"

    return StreamingResponse(body(), media_type="application/x-ndjson")


@agent_router.get("/ask")
async def ask_get(request: Request):
    # Redirect GET requests to / with error message
    return templates.TemplateResponse(name="index.html", request=request, context={
        "response": "",
        "error": "You need to provide 'input' to ask the agent"
    })


@agent_router.post("/ask")
async def ask(request: Request):
    try:
        form = await request.form()

        run_id = form.get("run_id")
        if run_id:
            events = resume_events(request, run_id, form.get("permission_decision") == "y")
            return render_index(request, **await run_in_threadpool(page_context, events))

        user_input = form.get("input")

        if not user_input:
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": "",
                "error": "You need to provide 'input' to ask the agent"
            })

        events = agent_events(request, user_input)
        return render_index(request, **await run_in_threadpool(page_context, events))

    except Exception as e:
        return templates.TemplateResponse(name="index.html", request=request, context={
            "response": "",
            "error": str(e)
        })


@agent_router.post("/ask_stream")
async def ask_stream(request: Request):
    form = await request.form()

    request_id = str(form.get("request_id") or "")
    request_id = request_id if REQUEST_ID_RE.match(request_id) else None
    owner = session_owner(request)

    # Answer to a permission card: continue the parked run
    run_id = form.get("run_id")
    if run_id:
        return ndjson_response(resume_events(request, run_id, form.get("permission_decision") == "y"), request_id, owner)

    user_input = form.get("input")

    if not user_input:
        async def error_gen():
            yield serialize_stream_event({"event": "error", "message": "You need to provide 'input' to ask the agent"}) + "\n"
        return StreamingResponse(error_gen(), media_type="application/x-ndjson")

    return ndjson_response(agent_events(request, user_input), request_id, owner)


@agent_router.post("/ask_stream/stop")
async def stop_stream(request: Request):
    """Stop a running streamed request and discard everything it left behind (core/cancel.py)."""
    form = await request.form()
    active = cancel.stop(str(form.get("request_id") or ""), owner=session_owner(request))
    if active is None:
        return {"stopped": False}

    await run_in_threadpool(active.done.wait, cancel.STOP_WAIT_SECONDS)
    done = [name for name, _ in active.actions if name and name not in READ_ONLY_TOOLS]
    return {"stopped": True, "finished": active.done.is_set(), "already_done": done}


@agent_router.post("/conversation/new")
async def new_conversation(request: Request):
    """Start a fresh conversation: later questions no longer see the earlier ones (search_history still can)."""
    session_conversation(request, new=True)
    return {"ok": True}
