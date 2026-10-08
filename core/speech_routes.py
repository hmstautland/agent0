import os
import shutil

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from core.auth import is_logged_in
from core.speech_to_text import transcribe_audio
from core.templates import templates
from core.text_to_speech import (
    DEFAULT_DIALOGUE_VOICE_A,
    DEFAULT_DIALOGUE_VOICE_B,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_SPEED,
    DEFAULT_VOICE,
    MAX_SPEED,
    MIN_SPEED,
    OUTPUT_FORMATS,
    convert_audio_file,
    extract_text_from_document,
    get_voices,
    synthesize,
    synthesize_dialogue,
)
from tools.audio import find_audio_files
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


@speech_router.get("/tts/voices")
async def tts_voices():
    return {
        "voices": get_voices(),
        "default": DEFAULT_VOICE,
        "formats": sorted(OUTPUT_FORMATS),
        "default_format": DEFAULT_OUTPUT_FORMAT,
        "speed": {"min": MIN_SPEED, "max": MAX_SPEED, "default": DEFAULT_SPEED},
        "dialogue_default": {"voice_a": DEFAULT_DIALOGUE_VOICE_A, "voice_b": DEFAULT_DIALOGUE_VOICE_B},
    }


@speech_router.get("/tts/files")
async def tts_files(q: str = None):
    """List/search saved audio files (local_storage/audio) for the dashboard's
    "Play a saved file" panel - the same lookup tools.audio.play_audio_file
    uses for the chat-driven "play ..." shortcut.
    """
    matches = find_audio_files(q)
    return {"files": [{"filename": f.name, "audio_url": f"/audio/{f.name}"} for f in matches]}


@speech_router.post("/tts")
async def tts(request: Request):
    form = await request.form()
    text = form.get("text")
    voice_id = form.get("voice") or None
    speed = form.get("speed") or DEFAULT_SPEED
    output_format = form.get("output_format") or DEFAULT_OUTPUT_FORMAT
    title = form.get("title") or None

    try:
        result = await run_in_threadpool(synthesize, text, voice_id, speed, output_format, title)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    filename = os.path.basename(result["path"])
    return {
        "audio_url": f"/audio/{filename}",
        "filename": filename,
        "mime_type": result["mime_type"],
    }


@speech_router.post("/tts/convert")
async def tts_convert(request: Request):
    form = await request.form()
    upload = form.get("file")
    output_format = form.get("output_format") or DEFAULT_OUTPUT_FORMAT

    if upload is None or not getattr(upload, "filename", None):
        return JSONResponse({"error": "No file provided"}, status_code=400)

    try:
        result = await run_in_threadpool(convert_audio_file, upload.file, upload.filename, output_format)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    filename = os.path.basename(result["path"])
    return {
        "audio_url": f"/audio/{filename}",
        "filename": filename,
        "mime_type": result["mime_type"],
    }


@speech_router.post("/tts/extract-text")
async def tts_extract_text(request: Request):
    form = await request.form()
    upload = form.get("file")

    if upload is None or not getattr(upload, "filename", None):
        return JSONResponse({"error": "No file provided"}, status_code=400)

    try:
        text = await run_in_threadpool(extract_text_from_document, upload.file, upload.filename)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return {"text": text}


@speech_router.post("/tts/dialogue")
async def tts_dialogue(request: Request):
    form = await request.form()
    text = form.get("text")
    voice_a = form.get("voice_a") or None
    voice_b = form.get("voice_b") or None
    speed = form.get("speed") or DEFAULT_SPEED
    output_format = form.get("output_format") or DEFAULT_OUTPUT_FORMAT
    title = form.get("title") or None

    try:
        result = await run_in_threadpool(synthesize_dialogue, text, voice_a, voice_b, speed, output_format, title)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    filename = os.path.basename(result["path"])
    return {
        "audio_url": f"/audio/{filename}",
        "filename": filename,
        "mime_type": result["mime_type"],
    }
