@REM UI Launcher
@echo off
cd /d C:\AI\projects\agent0

call .\venv\Scripts\activate.bat

uvicorn core.ui:app --reload

pause