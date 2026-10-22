# How Ollama works

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md) · [Step 1](01-install-ollama.md)

Ollama is a small background server that downloads models, loads them into RAM/VRAM and serves them over HTTP. It is to LLMs roughly what Docker is to containers: `pull` fetches an image, a daemon runs it, and a CLI plus an API talk to the daemon.

```
your code / terminal ──HTTP──► ollama server (localhost:11434) ──► model in RAM/GPU
```

- **It runs as a service.** The installer starts it automatically (a systemd service on Linux, a menu-bar app on macOS/Windows). If it isn't running, start it with `ollama serve`. You only need one instance.
- **The `ollama` command is just a client** of that server. `ollama run`, `ollama pull`, `ollama list` and `ollama ps` all call the same HTTP API your code will use, so anything the CLI can do, your program can do too.
- **Reachable from a standard terminal, yes.** It listens on `127.0.0.1:11434`, so `curl` works with no API key and no login:

  ```bash
  curl http://localhost:11434/api/tags      # list installed models
  curl http://localhost:11434/api/chat -d '{
    "model": "qwen3:8b",
    "messages": [{"role": "user", "content": "say hi"}],
    "stream": false
  }'
  ```

  If `curl` answers, Python will too. This is the first thing to try when something fails. (Windows PowerShell: use `curl.exe`, since plain `curl` is an alias for something else.)
- **Local only by default.** It binds to localhost, so other machines can't reach it and nothing leaves your computer. To serve another machine, set `OLLAMA_HOST=0.0.0.0` on the server. There's no authentication, so only do that on a trusted network.
- **Models load on first use, then stay warm.** The first request after a pause is slow (the weights are loading). Ollama unloads an idle model after about 5 minutes. `ollama ps` shows what's loaded and whether it's on GPU or CPU.
- **Models are files on disk** (`~/.ollama/models`, several GB each). Remove one with `ollama rm <name>`.
- **No GPU?** It still works on CPU, just slower. Use a 3B–8B model.
- **It's stateless.** The server doesn't remember conversations; your code resends the history on every call ([Step 2](../BUILD_YOUR_OWN_AGENT.md#step-2-talk-to-the-model)).
- **Two endpoints exist:** `/api/generate` (one prompt in, one answer out) and `/api/chat` (a list of messages, plus tool calling). Agents use `/api/chat`.
