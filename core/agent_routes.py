import json
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

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
    return stream_agent(user_input, owner=session_owner(request), granted=session_grants(request))


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


def ndjson_response(events):
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

        shortcut = shortcut_text_response(user_input)
        if shortcut is not None:
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": shortcut,
            })

        # Shortcut: "add a meeting ..." - create it and open the calendar on
        # the new event's month (or reply asking to restate the date/time)
        calendar_result = create_event_from_command(user_input)
        if calendar_result is not None:
            return render_index(request, **page_context([{"event": "final_response", **calendar_result}]))

        # Shortcut: "play ..." requests, bypass the LLM and hand the web UI a
        # concrete file to play, or candidates to choose between
        audio_result = audio_play_result(user_input)
        if audio_result is not None:
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": describe_play_result(audio_result),
                "audio_data": audio_result,
            })

        # Shortcut: if the user asked to see their calendar, bypass the LLM
        # and open the month-grid calendar (features/calendar), which fetches
        # its own data from GET /calendar/month.
        if is_calendar_request(user_input):
            year, month = calendar_target_month(user_input)
            return templates.TemplateResponse(name="index.html", request=request, context={
                "response": "",
                "calendar_month": {"year": year, "month": month},
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

    # Answer to a permission card: continue the parked run
    run_id = form.get("run_id")
    if run_id:
        return ndjson_response(resume_events(request, run_id, form.get("permission_decision") == "y"))

    user_input = form.get("input")

    if not user_input:
        async def error_gen():
            yield serialize_stream_event({"event": "error", "message": "You need to provide 'input' to ask the agent"}) + "\n"
        return StreamingResponse(error_gen(), media_type="application/x-ndjson")

    shortcut = shortcut_text_response(user_input)
    if shortcut is not None:
        async def shortcut_gen():
            yield serialize_stream_event({"event": "final_response", "response": shortcut}) + "\n"
        return StreamingResponse(shortcut_gen(), media_type="application/x-ndjson")

    calendar_result = create_event_from_command(user_input)
    if calendar_result is not None:
        return ndjson_response([{"event": "final_response", **calendar_result}])

    audio_result = audio_play_result(user_input)
    if audio_result is not None:
        async def audio_gen():
            yield serialize_stream_event({
                "event": "final_response",
                "response": describe_play_result(audio_result),
                "audio": audio_result,
            }) + "\n"
        return StreamingResponse(audio_gen(), media_type="application/x-ndjson")

    if is_calendar_request(user_input):
        year, month = calendar_target_month(user_input)

        async def calendar_gen():
            yield serialize_stream_event({
                "event": "final_response",
                "response": "",
                "show_calendar": {"year": year, "month": month},
            }) + "\n"
        return StreamingResponse(calendar_gen(), media_type="application/x-ndjson")

    return ndjson_response(agent_events(request, user_input))
