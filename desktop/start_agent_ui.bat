@REM UI Launcher
@echo off
cd /d C:\AI\projects\agent0

call .\venv\Scripts\activate.bat

start /min ollama serve

uvicorn core.ui:app --host 0.0.0.0 --port 8000

pause