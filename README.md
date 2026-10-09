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

- Local LLM via Ollama; tries a direct answer first, escalates to the tool loop when tools are needed
- Permission-gated tools (safe by default), diff preview before file writes, project-sandboxed file access
- Web search (DuckDuckGo) and page reading, calendar, notes, saved-audio playback
- Text-to-speech (Kokoro) and speech-to-text (faster-whisper) from the web UI
- All actions logged to `local_storage/logs.txt`

## Layout

```
agent.py          agent loop (CLI + streaming web)
config/           settings (permission rules), system prompt
core/             llm, permission, logger, diff, FastAPI app + routes, STT
tools/            tools the LLM can call (registry.py declares them)
features/         calendar/, audio/ (TTS, player) - routes, static, templates
templates/        index.html + shared components
tests/            pytest suite
```

See `CLAUDE.md` for architecture details.

## Setup

Create and activate the virtual environment:

```
python -m venv venv
source venv/bin/activate.fish     # Linux (fish); bash: source venv/bin/activate
.\venv\Scripts\Activate.ps1       # Windows PowerShell
venv\Scripts\activate.bat          # Windows CMD
```

Install and pull models:

```
pip install -r requirements.txt

ollama serve                      # usually already a service
ollama pull qwen3:8b              # direct answers
ollama pull qwen3-coder:30b       # tool loop (files/code)
```

Run:

```
uvicorn core.ui:app --reload      # web UI at http://127.0.0.1:8000
python -m agent                   # CLI
python -m pytest                  # tests
```

### Windows shortcut (`.bat`)

```
@echo off
cd /d C:\AI\projects\agent0
call venv\Scripts\activate.bat
uvicorn core.ui:app
pause
```

## Ollama environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_MODEL` | `qwen3:8b` | Light model for direct answers |
| `OLLAMA_CODE_MODEL` | `qwen3-coder:30b` | Model for the tool loop |
| `OLLAMA_NUM_CTX` | `16384` | Context window (Ollama's 4096 default silently truncates source files) |
| `OLLAMA_TIMEOUT` | `600` | Request timeout (seconds) |

To run everything on the light model: `set -x OLLAMA_CODE_MODEL qwen3:8b` (fish). To switch models, `ollama pull <model>` and set the variable above.

## Text-to-Speech (Kokoro-82M)

Open the dashboard with the 🗣️ icon in the chat bar. Weights download from Hugging Face on first use of an accent into `KOKORO_CACHE_DIR`, then everything runs offline.

**ffmpeg** is required for MP3/OGG output and file conversion (WAV/FLAC are native): `sudo pacman -S ffmpeg` or `sudo apt install ffmpeg`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TTS_DEVICE` | `auto` | `auto` (CUDA if available), `cpu`, or `cuda` |
| `KOKORO_CACHE_DIR` | `models/kokoro` | Model weight cache |

| Endpoint | Purpose |
| --- | --- |
| `POST /tts` | Generate speech (`text`, `voice`, `speed`, `output_format`, `title`) |
| `POST /tts/dialogue` | Two-speaker dialogue (`text`, `voice_a`, `voice_b`, `speed`, `output_format`, `title`) |
| `POST /tts/convert` | Re-encode an audio file (`file`, `output_format`) |
| `POST /tts/extract-text` | Extract text from a document (`file`) |
| `GET /tts/voices` | Voices, formats, speed range and defaults |
| `GET /tts/files` | List/search saved audio (`q`) |

All routes require a logged-in session (401 otherwise). Output goes to `local_storage/audio/`.

**Limits and defaults**: speed 0.5-2.0 (default 1.0); formats `wav` (default), `mp3`, `flac`, `ogg`; max 10,000 words per request; default voice Isabella.

**Voices** (British English): Alice, Emma, Isabella, Lily (female); Daniel, Fable, George, Lewis (male).

**Dialogue**: prefix each line with `A:` or `B:` (case-insensitive). Each speaker gets their own voice (defaults: A Isabella, B George), turns are joined with a 0.3s gap, consecutive lines from one speaker are merged, and unprefixed lines are rejected.

```
A: Have you tried the new coffee place?
B: Not yet, is it any good?
```

**Documents**: drop or browse a `.txt`, `.md`/`.markdown` or `.docx` (max 20MB) to fill the text box. Markdown is flattened to speakable text (`.md` only, not typed text); `.doc` is unsupported.

**File names**: the optional `title` is sanitized and deduplicated (`My Clip.wav`, `My Clip_2.wav`); blank gives `tts_<date>_<HH-MM>`. A dialog shows the saved file with a "Play now" button; nothing autoplays.

**Convert**: input must be WAV/MP3/FLAC/OGG, max 100MB; ffmpeg re-encodes without running Kokoro. Output is named `converted_<timestamp>.<ext>`.

Kokoro-82M is released by [hexgrad](https://huggingface.co/hexgrad/Kokoro-82M) under Apache 2.0.

## Examples

```
"What is in the news in Brazil?"
"Read my calendar tool and add logging"
"Summarize this file"
```

## Limitations

- No persistent memory
- Web access is search (DuckDuckGo) plus plain-text page fetch: no JavaScript rendering, clicking or logins
