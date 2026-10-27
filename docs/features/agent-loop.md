# Agent loop and models

Every request from the web UI or the CLI goes through one loop (`agent.py`, `_run_steps`). It runs entirely against a local Ollama server, and no hosted AI API is involved.

## Using it

Ask anything in the chat box (web) or at the `>>` prompt (`python -m agent`). The web UI streams the model's thinking and answer live next to the thinking image. The stop button cancels a running request.

## How it works

1. **Shortcuts first.** Some requests are recognised by pattern before any model runs: "add a meeting ..." ([calendar](calendar.md)), "play ..." ([audio playback](audio-playback.md)), and "move the scripts out of <file>.html". The web UI also catches "show my calendar" and "note ..." ([notes](notes.md)).
2. **Direct answer.** The general model (`OLLAMA_MODEL`) answers on its own if it can. Otherwise it replies `needs_tools` (it runs the tool loop itself) or `needs_code` (the code model runs it).
3. **Routing without asking.** Requests that clearly need tools skip step 2: anything naming code files (`.py`, `.html`, `.js`, ...), templates or code identifiers goes to the code model (`OLLAMA_CODE_MODEL`). Text files (`.md`, `.txt`) and plain file handling go to the general model's tool loop.
4. **Tool loop.** The model calls tools through Ollama's tool calling (declared in `tools/registry.py`), sees the results, and repeats until it gives a plain answer or hits `MAX_STEPS`. Calls that need approval pause the run (see [permissions](permissions.md)).

**Context.** Ollama silently drops whatever overflows the context window, so `core/context.py` trims the history itself. One oversized tool result is cut when it's added. Before each model call, older tool results are replaced with a short stub saying they can be fetched again, and the newest 2 are always kept whole. The model doesn't summarise anything, so the exact text that `edit_file` needs is never paraphrased.

**Stop button.** It cancels the request at its next event and closes the connection to Ollama, so generation stops. The request's log lines are removed and the turn isn't stored. Tool calls that already ran, such as a file edit, are not undone, and the stop reply lists them.

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_MODEL` | `qwen3.6:35b` | General model: direct answers, and the tool loop for tasks that aren't about code (must support Ollama tool calling) |
| `OLLAMA_CODE_MODEL` | `qwen3-coder:30b` | Model for the tool loop when the task is about code or project files (must support Ollama tool calling) |
| `OLLAMA_CHAT_URL` | `http://localhost:11434/api/chat` | Local chat endpoint |
| `OLLAMA_NUM_CTX` | `32768` | Context window for the general model (Ollama's 4096 default silently truncates) |
| `OLLAMA_CODE_NUM_CTX` | `32768` | Context window for the code model (it accumulates file reads) |
| `OLLAMA_TIMEOUT` | `600` | Request timeout (seconds) |
| `READ_WHOLE_FILE_MAX_LINES` | `400` | Longer files are read as an outline; the model then asks for a section with `start_line`/`end_line` |
| `MAX_STEPS` | `8` | Tool-loop step limit per request |

The context window is set per model, not per call, because Ollama reloads a model whenever `num_ctx` changes.

On the dev machine (58 GB RAM, `qwen3-coder:30b` fully on GPU), `num_ctx` 8192 uses 19 GB and 32768 uses 21 GB. Load time (~9 s) and generation speed (~85-89 tok/s) are about the same, so the larger window costs little. It's the prompt length that determines processing time.

To run everything on one model: `set -x OLLAMA_CODE_MODEL qwen3.6:35b` (fish). To go back to the old light model: `set -x OLLAMA_MODEL qwen3:8b`. To switch models, `ollama pull <model>` and set the variable.

## Limits

- The stop button can take a moment while Ollama is still reading the prompt or a tool is running.
- Parked approvals and running requests are in-memory, so a server restart drops them.
