# Step 1: Install a local model

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md)

Install Ollama from [ollama.com/download](https://ollama.com/download) (installer for Windows and macOS; a one-line script for Linux). Then, in a terminal:

```bash
ollama pull qwen3:8b        # small, fits most laptops; supports tool calling
ollama run qwen3:8b "say hi"
```

Pick a model that lists **tools** support on [ollama.com/library](https://ollama.com/library). Bigger = smarter but slower; start small. agent0 uses `qwen3.6:35b` (general) and `qwen3-coder:30b` (code) on a GPU machine (`core/llm.py`).

Quick check that everything's ready:

```bash
ollama list                    # is the model there?
curl -s localhost:11434        # prints "Ollama is running"
```

Related:
- [How Ollama works](how-ollama-works.md): the server, `curl`, ports, what stays loaded.
- [Choose a model for your PC](choose-a-model.md): a prompt that finds a good match for your hardware.
