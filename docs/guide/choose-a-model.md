# Choose a model for your PC

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md) · [Step 1](01-install-ollama.md)

The right model depends on your memory and GPU. Two parts: collect your specs, then give them to any AI assistant with the prompt below.

## 1. Collect your specs

| OS | Command |
|---|---|
| **Windows** (PowerShell) | `Get-CimInstance Win32_VideoController \| Select Name,AdapterRAM` and `systeminfo \| findstr /C:"Total Physical Memory"`. For NVIDIA also `nvidia-smi` |
| **macOS** | `system_profiler SPHardwareDataType` (chip and memory; Apple Silicon shares memory between CPU and GPU) |
| **Linux** | `free -h`, `lscpu \| head -20`, `lspci \| grep -i vga`; for NVIDIA `nvidia-smi`, for AMD `rocm-smi` |

You want: **RAM**, **GPU name**, **GPU memory (VRAM)**, and whether it's an Apple Silicon Mac.

## 2. Ask for a recommendation

Paste this into any AI chat, replacing the bracketed parts. Run the `ollama list` / `ollama ps` part yourself if you already have Ollama.

```text
I'm building a local AI agent with Ollama. It calls tools (read files, search,
calendar) in a multi-step loop, so the model MUST support tool calling.

My machine:
- OS: [Windows / macOS / Linux]
- RAM: [e.g. 16 GB]
- GPU: [name, or "none"]
- VRAM: [e.g. 8 GB, or "unified memory" on Apple Silicon]
- Free disk space: [e.g. 50 GB]

Recommend 3 models I can pull from the Ollama library, in order:
1. the safest choice that will run smoothly on my hardware
2. a smarter one that is still usable (say how slow it will be)
3. the smallest fallback if the others are too slow

For each give: the exact `ollama pull` tag (with size/quantization), roughly how
much memory it needs, whether it fits fully in my VRAM or spills to the CPU, and
the speed I should expect (tokens/second, roughly).

Rules:
- Only recommend models that list "tools" support on ollama.com/library.
- If you are not sure a tag exists or supports tools, say so; do not invent tags.
- A model must fit in memory with room to spare: it also needs space for the
  context window (I plan to use a 16k-32k context).
- Tell me how to verify the choice with `ollama pull`, `ollama ps` and a
  tool-calling test.
```

## 3. Sanity-check the answer

AI assistants can be out of date or confidently wrong about model names. Always verify:

- **The tag exists and lists "tools":** open [ollama.com/library](https://ollama.com/library), find the model, check its tags and capabilities.
- **It fits:** after `ollama run <tag> "hi"`, run `ollama ps`. The `PROCESSOR` column should say `100% GPU` for best speed. `x% CPU` means it is spilling into system memory and will be slower.
- **Rule of thumb:** a 4-bit model needs roughly 0.6 GB of memory per billion parameters, plus 1–3 GB for the context window. So 8B ≈ 5–6 GB and 30B ≈ 20 GB or more.
- **Too slow or running out of memory?** Go one size down before changing anything else.
- **Doesn't call tools?** Try the next size up, or a different model family, before blaming your code.
