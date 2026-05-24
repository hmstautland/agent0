from agent import run_agent, run_agent_local
from core.permission import PermissionRequired
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

        permission_decision = form.get("permission_decision")
        permission_action = form.get("permission_action")
        permission_args = form.get("permission_args")
        permission_risk = form.get("permission_risk")
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
                    },
                    "input": user_input,
                })

        if not isinstance(response, str):
            response = json.dumps(response, indent=2)

        return templates.TemplateResponse(name="index.html", request=request, context={    
            "response": str(response)
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