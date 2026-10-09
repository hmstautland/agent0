import shutil

from fastapi import APIRouter, Depends, File, Request, UploadFile

from core.auth import is_logged_in
from core.speech_to_text import transcribe_audio
from core.templates import templates
from tools.notes import parse_note_command, save_note_text

speech_router = APIRouter(dependencies=[Depends(is_logged_in)])


@speech_router.post("/speech")
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


@speech_router.get("/speech")
async def speech_get(request: Request):
    # Redirect GET requests to / with error message
    return templates.TemplateResponse(name="index.html", request=request, context={
        "response": "",
        "error": "You need to provide audio input to the speech endpoint"
    })
