"""HTTP surface of the CV feature: the "tailor CV + cover letter" form (text or file
upload for the master CV and the role description) and the download of the
generated .docx files. The writing itself is tools/documents.py - the same code
the agent's tailor_application tool runs. Static assets (features/cv/static) are
served at /static/cv."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from core.auth import is_logged_in
from tools import documents

STATIC_DIR = Path(__file__).resolve().parent / "static"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# What documents.tailor() names its files; nothing else is ever served
GENERATED_NAME_RE = re.compile(r"^(?:cv|cover-letter)_[a-z0-9-]+_\d{8}_\d{6}_\d{6}\.docx$")

logger = logging.getLogger(__name__)

cv_router = APIRouter(dependencies=[Depends(is_logged_in)])


async def _field(form, text_key, file_key):
    """The text typed into the form, or - when a file was chosen - the text of that file (the file wins)."""
    upload = form.get(file_key)
    if upload is not None and getattr(upload, "filename", None):
        return await run_in_threadpool(documents.read_upload, upload.file, upload.filename)
    return str(form.get(text_key) or "")


@cv_router.post("/cv/tailor")
async def cv_tailor(request: Request):
    form = await request.form()
    try:
        master = await _field(form, "master_text", "master_file")
        role = await _field(form, "role_text", "role_file")
    except ValueError as e:
        logger.warning("Invalid CV tailor request data", exc_info=True)
        return JSONResponse({"error": "Invalid input provided."}, status_code=400)

    result, error = await run_in_threadpool(documents.tailor, master, role, form.get("company"))
    if error:
        return JSONResponse({"error": error[0].upper() + error[1:]}, status_code=400)

    return {
        "cv": result["cv"],
        "letter": result["letter"],
        "cv_url": f"/cv/files/{result['cv_path'].name}",
        "letter_url": f"/cv/files/{result['letter_path'].name}",
    }


@cv_router.get("/cv/files/{name}")
async def cv_file(name: str):
    path = documents.CV_FOLDER / name
    if not GENERATED_NAME_RE.match(name) or not path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path, media_type=DOCX_TYPE, filename=name)


def cv_static_files():
    return StaticFiles(directory=str(STATIC_DIR))
