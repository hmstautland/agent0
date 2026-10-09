import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from agent import run_agent, stream_agent
from core.auth import is_logged_in
from core.permission import PermissionRequired
from core.streaming import serialize_stream_event
from core.templates import templates
from features.calendar.calendar import (
    calendar_target_month,
    create_event,
    is_calendar_request,
    parse_create_command,
)
from features.audio.player import describe_play_result, parse_play_command, play_audio_file
from tools.notes import parse_note_command, save_note_text

agent_router = APIRouter(dependencies=[Depends(is_logged_in)])


def render_index(request: Request, **context):
    return templates.TemplateResponse(name="index.html", request=request, context=context)


def create_permission_decisions(form):
    permission_decision = form.get("permission_decision")
    permission_action = form.get("permission_action")

    if permission_decision is None or permission_action is None:
        return {}

    return {permission_action: permission_decision == "y"}


def shortcut_text_response(user_input):
    """Handle note-taking and calendar-creation requests that bypass the LLM.

    The local model isn't reliable at recognizing these need a specific tool
    rather than answering "I can't do that" directly. Returns response text,
    or None if user_input isn't one of these shortcuts.
    """
    note_text = parse_note_command(user_input)
    if note_text is not None:
        note_file = save_note_text(note_text, source="text")
        return f"Note saved to {note_file}"

    calendar_command = parse_create_command(user_input)
    if calendar_command is not None:
        result = create_event(**calendar_command)
        return f"{result}\n\nWould you like to see your calendar?"

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

        permission_decisions = create_permission_decisions(form)

        try:
            response = run_agent(user_input, permission_decisions=permission_decisions)
        except PermissionRequired as pr:
            return render_index(request,
                response="",
                permission={
                    "action": pr.action,
                    "args": json.dumps(pr.tool_args),
                    "risk": pr.risk,
                    "reason": pr.reason,
                },
                input=user_input,
            )

        # A read_calendar tool result (chosen by the LLM) is shown as the
        # month-grid calendar instead of being flattened into text.
        calendar_month = None
        if isinstance(response, dict) and response.get("show_calendar"):
            calendar_month = response["show_calendar"]
            response = ""

        if not isinstance(response, str):
            response = json.dumps(response, indent=2)

        return templates.TemplateResponse(name="index.html", request=request, context={
            "response": response,
            "calendar_month": calendar_month,
        })

    except Exception as e:
        return templates.TemplateResponse(name="index.html", request=request, context={
            "response": "",
            "error": str(e)
        })


@agent_router.post("/ask_stream")
async def ask_stream(request: Request):
    form = await request.form()
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

    async def event_stream():
        for message in stream_agent(user_input):
            yield serialize_stream_event(message) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
