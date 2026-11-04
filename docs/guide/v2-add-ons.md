# v2 add-ons

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md)

Each item is small and independent. Add what you need, in any order.

### Add a logger
Append one JSON line per event (question, tool call, result, error, timing) to `local_storage/logs.txt`. When the agent does something odd, this is how you find out why. Make it self-pruning so it can't grow forever. *agent0:* `core/logger.py`.

### Add local storage
Use SQLite (`sqlite3` is in the standard library). One `connect()` helper, one `schema.sql`, one module per kind of data. Keep persistence separate from what the data means. Put everything under a git-ignored `local_storage/`. *agent0:* `storage/db.py`, `storage/schema.sql`.

### Add conversation memory
Store each finished turn (question, answer, one-line summary of tools used) in SQLite. Before each model call, insert the newest few turns between the system prompt and the new question. Store **summaries of tool calls, not raw tool results**; they are huge. Add FTS5 full-text search and expose it as a `search_history` tool for older sessions. *agent0:* `core/conversations.py`, `storage/conversations.py`.

### Add context files
A markdown file the model (or any AI coding tool) reads first: what the project is, layout, conventions, what not to touch. Two kinds:
- **Project context** (`CLAUDE.md`, `README.md`): architecture and rules, for whoever edits the code.
- **User/builder context** (`context.md`): who you are, what you own, when AI should ask first.

For your *runtime* agent, load such a file into the system prompt at startup (`SYSTEM_PROMPT + Path("context.md").read_text()`). Keep it short; every word costs context window. *agent0:* `CLAUDE.md`, `context.md`.

### Add skills
A skill is a markdown file of instructions for one kind of task ("how to write a weekly report"). Don't load all of them into the prompt. Put one line per skill in the system prompt (name + when to use it) and give the agent a `load_skill(name)` tool that returns the full text on demand. It's just another tool. Two cautions from testing with local models: answer-first routing can skip the tool loop entirely (agent0 lists the skills in the local-first prompt too), and a model may simply not call `load_skill`. Keep any rule that protects data in the system prompt itself, and use a skill for how-to detail. *agent0:* `tools/skills.py` and `skills/weekly-report.md`; a skill is a markdown file with `name`/`description` frontmatter.

### Add a stop button
Long runs need a cancel. Stream the model response, keep a per-run cancel flag, and close the HTTP connection to Ollama when it's set. *agent0:* `core/cancel.py`, `core/llm.py::chat_stream`.

### Add streaming
Use `"stream": true` and forward chunks to the browser (Server-Sent Events) so users see the model "thinking" live instead of staring at a spinner. *agent0:* `core/llm.py::chat_stream`, `core/streaming.py`.

### Add context pruning
The loop appends every file read and search result, so history grows until the model's window overflows. Cap any single oversized result and replace the oldest tool results with a stub like `[old result removed]`, keeping the newest two or so. Send the model a pruned *copy*; keep the full history for yourself. *agent0:* `core/context.py`.

### Add a speaker, text-to-speech
Run a local TTS model (Kokoro-82M) behind a `/tts` endpoint and a speaker button in the UI. It's a plain UI feature, not a tool; the agent never needs to call it. Needs `ffmpeg` for MP3/OGG. *agent0:* `features/audio/`; see README's "Text-to-Speech".

### Add a mic, speech-to-text
`faster-whisper` transcribes locally. Record in the browser, POST the audio to `/speech`, put the text into the input box. Also a plain UI feature. *agent0:* `core/speech_to_text.py`, `core/speech_routes.py`.

### Add shortcuts for things the model gets wrong
Small models are unreliable at "add a meeting tomorrow at 3". Detect those with a regex before the model runs and handle them in plain code. Escalate to the model only when no shortcut matches. *agent0:* `features/calendar/`, `core/agent_routes.py`.

### Add a second model
A fast general model for answers, a stronger one for multi-step file edits. Route by simple rules (file extension, keywords). *agent0:* `tool_route()` in `agent.py`.

### Add tests
Stub the model call with a fake that returns scripted messages, then assert on which tools ran. You can test the whole loop without Ollama. *agent0:* `tests/test_agent_flow.py` (`fake_chat`).
