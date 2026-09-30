# agent0

A local-first AI agent: FastAPI web UI + CLI, a multi-step tool-calling agent loop, and local-only models (Ollama for text, Kokoro for speech, faster-whisper for transcription). **No Anthropic/Claude API calls anywhere in the runtime** — `core/llm.py` only talks to a local Ollama server.

Read this file before re-exploring the codebase from scratch. It's a fast-moving repo (TTS in particular has been rewritten more than once) — if something here looks stale, trust the code and update this file rather than assuming the file is wrong and re-deriving everything.

## Architecture

```
User (CLI / web UI / voice)
    -> agent.py: _run_steps (multi-step tool loop)
    -> core/permission.py: approve/deny (config/settings.py RULES)
    -> tools/*.py, declared in tools/registry.py
    -> core/llm.py -> Ollama (qwen3 for direct answers, qwen3-coder for the tool loop)
```

- **`core/ui.py`** — FastAPI app assembly: mounts `/static`, `/media`, `/favicon`, `/audio`; includes `agent_router`, `speech_router`, `logout_router`, then `public_router` last (it has a catch-all route, so anything after it would be shadowed).
- **`agent.py`** — the agent loop (`_run_steps`, shared by CLI's `run_agent` and the web's streaming `stream_agent`). Tries a local-only answer first (`try_local_answer`), escalates to the tool loop if the model says it needs tools.
- **`tools/registry.py`** — the tools the *LLM* can choose to call (file read/write/edit, web search, calendar). Each tool's risk level gates whether it needs approval; `config/settings.py`'s `RULES` overrides that per-action.
- **TTS/STT generation is NOT in `tools/registry.py`** — both STT (`/speech`, mic button) and TTS generation (`/tts*`, speaker button/dashboard) are direct UI actions that bypass the LLM/permission loop entirely, wired straight from `static/speech.js` / `static/tts.js`. This is deliberate, not an oversight — don't "fix" it by moving them into the registry unless asked.
- **`core/speech_to_text.py`** — faster-whisper, local.
- **`core/text_to_speech.py`** / **`core/speech_routes.py`** — Kokoro-82M based TTS with multiple endpoints (`/tts`, `/tts/voices`, `/tts/dialogue`, `/tts/convert`). Full details (voices, env vars, ffmpeg requirement for MP3/OGG, dialogue script format) are documented in **README.md's "Text-to-Speech" section** — read that instead of re-deriving it from the source.
- **`tools/audio.py`** (`play_audio_file`) — the one exception to "speech isn't a registry tool": finding and "playing" an already-saved file from `local_storage/audio/` by (partial) name or by number *is* a real `tools/registry.py` entry, because it's a genuine LLM-invokable action, not a media-generation pipeline. It's also given the same reliability shortcut as calendar/notes (`parse_play_command`, checked directly in `agent.py::_run_steps` and `core/agent_routes.py::audio_play_result`, both `/ask` and `/ask_stream`) since the local model can't be trusted to reach for it on its own. A "choose between several matches" result is *not* plain text - it rides along as a structured `audio` field on the `final_response` event (see `static/audio-player.js` / `templates/components/audio_play.html`), rendered as clickable buttons that just resubmit `"play number N"`. The candidate list for "number N" is process-local, in-memory state (`tools/audio._last_candidates`) - same single-user tradeoff as `core/speech_to_text.py`'s recording globals, not safe across concurrent users or a restart.

## Running things

```
source venv/bin/activate.fish   # or venv/bin/activate for bash
pip install -r requirements.txt
ollama serve                    # usually already running as a systemd service
uvicorn core.ui:app --reload    # web UI at http://127.0.0.1:8000
python -m agent                 # CLI mode
pytest                          # test suite
```

Full setup/model details (which Ollama models to pull, env vars, Windows instructions) are in README.md — don't duplicate them here.

## Conventions worth knowing before editing

- `write_file`/`edit_file` (in `tools/files.py`) back up the previous version to `<path>.bak` before writing — this is intentional, not garbage to clean up.
- After changing a template or static file, run the `verify_app` tool (`tools/verify.py`) — it compiles templates, resolves `{% include %}`, checks referenced `/static`/`/media`/`/favicon` files exist, and re-imports `core.ui`. The system prompt (`config/system_prompt.py`) already tells the LLM to do this for its own edits; do the same when editing by hand.
- `local_storage/` is gitignored, holds runtime state (notes, generated audio, `logs.txt`). `local_storage/logs.txt` is a JSONL event log that grows continuously (1000+ lines already) — `tail`/`grep` it, never read it in full.
- Downloaded model weights live under `models/` (gitignored) and are fetched lazily on first use, not at import time — don't try to pre-load them or make startup depend on them.
- `tests/` mirrors the module layout (`test_agent_flow.py`, `test_web_tools.py`, `test_speech_routes.py`, `test_text_to_speech.py`, `test_audio_tool.py`, ...) — check for an existing test file before assuming a module is untested.
