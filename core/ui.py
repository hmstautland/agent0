from agent import run_agent
from fastapi import UploadFile, File
import shutil
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from core.speech_to_text import transcribe_audio
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(name="index.html",request=request,context={"response":""})

@app.post("/ask")
async def ask(request: Request):
    try:
        form = await request.form()
        user_input = form.get("input")

        response = run_agent(user_input)

        if not isinstance(response, str):
            response = json.dumps(response, indent=2)

        return templates.TemplateResponse(name="index.html", request=request, context={    
            "response": str(response)
        })
    
    except Exception as e:
        return {"error": str(e)}
    
@app.post("/speech")
async def speech(file: UploadFile = File(...)):
    temp_path = "local_storage/temp.wav"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text = transcribe_audio(temp_path)

    return {"text": text}