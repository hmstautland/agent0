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

## 2. Start Ollama

```
ollama run mistral
```

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

- Small models may hallucinate code
- Tool arguments may need normalization
- No persistent memory yet
- No true web browsing (search + summarize only)

---

# ✅ Summary

This project is a modular, local-first AI agent capable of safe tool use, multi-step reasoning, and code interaction. It provides a strong foundation for building more advanced autonomous systems while maintaining control, transparency, and security.

---
