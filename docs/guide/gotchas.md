# Gotchas that cost people hours

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md)

- **`num_ctx` defaults to 4096 in Ollama**, and overflow is *silently truncated*. The model then loses its instructions and invents tool names. Set it explicitly (16k–32k) and keep it constant: Ollama reloads the model whenever it changes.
- **Small models call tools badly.** If it ignores tools or writes JSON into its answer, try a bigger model before rewriting your prompt. agent0 has a fallback parser for tool calls written as text (`agent.py`).
- **Errors go back to the model as text**, not exceptions. It can often fix its own bad arguments.
- **Always cap the loop and every tool result's size.**
- **Edits:** have the model use `edit_file(old_text, new_text)` instead of rewriting whole files, and back up before writing (`tools/files.py`).
- **Models are non-deterministic.** Test behaviour you care about; don't trust a single good run.
- **"Local" is a promise you have to keep.** Tools that call the web send data off your machine; mark them and ask once per session.
