# 📘 Project README — Local AI Agent (Ollama + Tools + UI)

## 🧠 Abstract

This project implements a local-first AI agent powered by Ollama (Mistral 7B) with a modular Python architecture. The agent supports multi-step reasoning, controlled tool usage, and a permission layer for safe interaction with external systems and local resources. It can perform tasks such as web search, file inspection, and calendar management, while maintaining security through explicit approval flows, logging, and sandboxed execution. A lightweight FastAPI-based dashboard provides a user interface, and the system is designed to be extensible toward more advanced agent capabilities.

---

# 🧱 Architecture Overview

```
User (CLI / UI / Voice)
        ↓
Agent Loop (multi-step reasoning)
        ↓
Permission Layer (approve/deny)
        ↓
Tool Layer (web, files, calendar)
        ↓
LLM (Ollama - Mistral)
```

---

# 📂 Project Structure

```
agent0/
├── agent.py                # main agent loop
├── config/
│   ├── settings.py         # rules, limits
│   └── system_prompt.py    # LLM behavior
├── core/
│   ├── llm.py              # ollama calls
│   ├── permission.py       # approval logic
│   ├── logger.py           # logging
│   ├── diff.py             # diff preview
│   └── ui.py               # FastAPI dashboard
├── tools/
│   ├── web.py
│   ├── calendar.py
│   ├── files.py
│   └── registry.py
├── templates/
│   └── index.html
├── storage/
│   └── logs.txt
├── venv/
└── start_agent.bat
```

---

# ⚙️ Features

## ✅ Core Capabilities

- Local LLM via Ollama (Mistral 7B)
- Multi-step reasoning agent loop
- Tool orchestration system
- Permission-based execution (safe-by-default)
- Logging of all actions

## 🧰 Tools

- 🌐 Web search (DuckDuckGo)
- 📂 File system access (restricted to project)
- 📅 Calendar (.ics or API-ready)
- 🧠 Project structure awareness

## 🔐 Security

- Explicit approval for high-risk actions
- File access sandboxing
- Diff preview before file writes
- Logging of all actions

## 🖥️ Interfaces

- CLI interaction
- FastAPI web dashboard
- (Optional) Speech-to-text input

---

# 🚀 How to Run

## 1. Activate Virtual Environment

### Linux(CatchyOS)
```
python -m venv venv
source venv/bin/activate.fish 
(or look in folder if using other terminals)
```

### PowerShell:

```
.\venv\Scripts\Activate.ps1
```

### CMD:

```
venv\Scripts\activate.bat
```

---

## Install
```
pip install -r requirements.txt
```

## 2. Start Ollama

Ollama runs one server that serves every model you have pulled - the model is
chosen per request by the agent, not by the server. So start the server and pull
the two models the agent uses (`ollama run <model>` is only an interactive chat
client and is not needed by the app):

```
ollama serve            # usually already running as a service
ollama pull qwen3:4b          # light, for direct answers
ollama pull qwen3-coder:30b   # heavy, for file/code work
```

### Model settings (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_MODEL` | `qwen3:8b` | Light model for direct answers (the local-first step) |
| `OLLAMA_CODE_MODEL` | `qwen3-coder:30b` | Heavier model used once a request escalates to the tool loop (reading/editing files) |
| `OLLAMA_NUM_CTX` | `16384` | Context window. Ollama's own default is 4096, which is too small to hold a source file plus the instructions - the overflow is silently dropped and the model starts replying with prose or invented tool names |
| `OLLAMA_TIMEOUT` | `600` | Request timeout in seconds |

Override either one per shell, for example to run everything on the light model:

```
set -x OLLAMA_CODE_MODEL qwen3:4b   # fish
```

Measured on a Ryzen AI Max+ 395 (CPU only), which is why `qwen3:4b` is the
default over `mistral:7b`:

| model | generation | prompt eval | admits it needs the file tools |
| --- | --- | --- | --- |
| `qwen3:4b` | 34 tok/s | 206 tok/s | yes |
| `mistral:7b` | 24 tok/s | 100 tok/s | no - invents an answer instead |

---

## 3. Run Agent (CLI)

```
python -m agent
```

---

## 4. Run Web UI

```
uvicorn core.ui:app --reload
```

Open:

```
http://127.0.0.1:8000
```

---

## 5. Windows Shortcut (.bat)

```
@echo off
cd /d C:\AI\projects\agent0
call venv\Scripts\activate.bat
uvicorn core.ui:app
pause
```

---

# 🗣️ Text-to-Speech (Kokoro-82M)

The TTS dashboard (open it via the 🗣️ icon in the chat bar) generates speech
with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), an 82M-parameter
open-weight TTS model.

### FFmpeg (for MP3 / OGG output)

WAV and FLAC are produced natively (no external tools, via `soundfile`). MP3
and OGG/Opus are encoded from that WAV with `ffmpeg`, which must be on
`PATH`:

```
sudo pacman -S ffmpeg      # Arch / CachyOS
sudo apt install ffmpeg    # Debian/Ubuntu
```

## CPU / CUDA configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TTS_DEVICE` | `auto` | `auto` picks CUDA if available, otherwise CPU. Set to `cpu` or `cuda` to force one. |
| `KOKORO_CACHE_DIR` | `models/kokoro` | Where Kokoro's downloaded model weights are cached. |

Each accent's model is loaded once, on first use, and
reused for every request after that - it is never reloaded per-request.

## Model cache behavior

On first use of an accent, Kokoro downloads its weights from Hugging Face
into `KOKORO_CACHE_DIR` (`models/kokoro` by default). Every request after
that is fully offline.

## Available voices

Only British English voices from the official Kokoro-82M voice pack are
offered (`GET /tts/voices` lists them):

- **Female:** Alice, Emma, Isabella, Lily
- **Male:** Daniel, Fable, George, Lewis

## Two-speaker dialogue

Enable "Two-speaker dialogue" in the TTS dashboard to turn a script into a
conversation between two voices in one audio file (`POST /tts/dialogue`,
taking `text`, `voice_a`, `voice_b`, `speed`, `output_format`).

Prefix every line of the input with `A:` or `B:` to mark who's speaking:

```
A: Have you tried the new coffee place?
B: Not yet, is it any good?
A: Really good, you should go.
```

Each line is synthesized with its speaker's selected voice and the turns are
concatenated with a short silence gap between them. Consecutive lines from
the same speaker are merged into one turn; a line with no `A:`/`B:` prefix is
rejected with a clear error. The dashboard defaults Speaker A to Isabella and
Speaker B to George.

## Converting an existing file

The dashboard's "Convert an existing file" drop zone (drag a file in, or
click to browse) re-encodes an existing WAV/MP3/FLAC/OGG file to a different
format without running Kokoro at all (`POST /tts/convert`, taking `file` and
`output_format`) - useful when you already have the audio you want and only
need a different format. Uploads are capped at 100MB and converted via
`ffmpeg`, so it requires the same `ffmpeg` install as MP3/OGG generation
above.

## License and attribution

Kokoro-82M's weights and inference code are released by
[hexgrad](https://huggingface.co/hexgrad) under the **Apache License 2.0**.
This project uses the `kokoro`/`misaki` packages and the model weights
unmodified under that license - see the
[model card](https://huggingface.co/hexgrad/Kokoro-82M) for full terms.


# 🔄 Switching Ollama Models

## Pull a new model

```
ollama pull llama3:8b
```

## Change model in code

In `core/llm.py` or wherever you call Ollama:

```python
MODEL = "mistral"
```

Change to:

```python
MODEL = "llama3:8b"
```

---

## Recommended Models

| Model     | Notes              |
| --------- | ------------------ |
| mistral   | fast, lightweight  |
| llama3:8b | better reasoning   |
| mixtral   | stronger but heavy |

---

# 🔁 Agent Flow

1. User input
2. LLM decides next action
3. Permission check
4. Tool executes
5. Result fed back to LLM
6. Repeat until complete

---

# 🧪 Example Usage

```
"What is in the news in Brazil?"
"Read my calendar tool and add logging"
"Summarize this file"
```

---

# ⚠️ Known Limitations

- No persistent memory yet
- No true web browsing (search + summarize only)


---

# ✅ Summary

This project is a modular, local-first AI agent capable of safe tool use, multi-step reasoning, and code interaction. It provides a strong foundation for building more advanced autonomous systems while maintaining control, transparency, and security.

---
