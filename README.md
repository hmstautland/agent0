# agent0

A local-first AI agent: FastAPI web UI + CLI, a multi-step tool-calling loop, and local-only models (Ollama for text, Kokoro for speech, faster-whisper for transcription). No hosted AI APIs.

```
User (CLI / web UI / voice)
  -> agent loop (multi-step)
  -> permission layer (approve/deny)
  -> tools (files, web search, calendar, notes, audio playback)
  -> Ollama
```

## Features

Each feature has its own page in [docs/features/](docs/features/):

- [Agent loop and models](docs/features/agent-loop.md): direct answers first, a tool loop when needed, context pruning, stop button
- [Permissions and file safety](docs/features/permissions.md): approval cards, project sandbox, automatic backups
- [Conversation memory](docs/features/conversation-memory.md) and [skills](docs/features/skills.md)
- [Web search](docs/features/web-search.md), [calendar](docs/features/calendar.md), [notes](docs/features/notes.md)
- [Speech-to-text](docs/features/speech-to-text.md), [text-to-speech](docs/features/text-to-speech.md), [audio playback](docs/features/audio-playback.md)
- [Event log](docs/features/event-log.md), [remote access over Tailscale](docs/features/remote-access.md)

Other docs: [CLAUDE.md](CLAUDE.md) (architecture), [docs/DECISIONS.md](docs/DECISIONS.md) (decision log), [docs/BUILD_YOUR_OWN_AGENT.md](docs/BUILD_YOUR_OWN_AGENT.md) (step-by-step guide).

To read or share the "Build your own agent" guide as plain HTML, run `python docs/build_html.py` and open `docs/html/index.html`. The folder works without a server, so you can zip it and send it.

## Layout

```
agent.py          agent loop (CLI + streaming web)
config/           settings (permission rules), system prompt
core/             llm, permission, logger, context, conversations, FastAPI app + routes, STT
storage/          SQLite persistence (conversation history)
tools/            tools the LLM can call (registry.py declares them)
features/         calendar/, audio/ (TTS, player) - routes, static, templates
skills/           markdown skills the agent loads on demand
templates/        index.html + shared components
docs/             feature docs, decision log, guide
tests/            pytest suite
```

## Setup

Create and activate the virtual environment:

```
python -m venv venv
source venv/bin/activate.fish     # Linux (fish); bash: source venv/bin/activate
.\venv\Scripts\Activate.ps1       # Windows PowerShell
venv\Scripts\activate.bat          # Windows CMD
```

Install and pull models (see [agent loop and models](docs/features/agent-loop.md) for the model settings):

```
pip install -r requirements.txt

ollama serve                      # usually already a service
ollama pull qwen3.6:35b           # direct answers + tool loop for general tasks
ollama pull qwen3-coder:30b       # tool loop for code/project files
```

Create `.env` in the project root with the web login password and a session secret. The secret signs the login cookie, and the web app refuses to start without one of at least 32 characters:

```
APP_LOGIN_PASSWORD=<your password>
SESSION_SECRET=<random value>      # python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run:

```
uvicorn core.ui:app --reload      # web UI at http://127.0.0.1:8000
python -m agent                   # CLI
python -m pytest                  # tests
```

On Windows, a shortcut `.bat`:

```
@echo off
cd /d C:\AI\projects\agent0
call venv\Scripts\activate.bat
uvicorn core.ui:app
pause
```

## Examples

```
"What is in the news in Brazil?"
"Read my calendar tool and add logging"
"Summarize this file"
"add a meeting with Ola tomorrow at 14"
"give me a weekly report"
```

## Limitations

- Single user: approvals, the "play number N" list and STT recording state live in process memory.
- Web access is search (DuckDuckGo) plus plain-text page fetch: no JavaScript rendering, clicking or logins.
