# Step 0: Prerequisites

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md)

You need Python 3.10+, a terminal and a code editor. Check what you have:

```bash
python3 --version     # Windows: python --version
```

If that prints 3.10 or higher, skip to "Project setup".

| | Install Python | Open a terminal |
|---|---|---|
| **Windows** | [python.org/downloads](https://www.python.org/downloads/windows/). **Tick "Add python.exe to PATH"** in the installer. Or `winget install Python.Python.3.12` | PowerShell or Windows Terminal. Use `python`, not `python3` |
| **macOS** | `brew install python` ([brew.sh](https://brew.sh)), or [python.org/downloads](https://www.python.org/downloads/macos/) | Terminal |
| **Linux** | Usually preinstalled. Otherwise `sudo apt install python3 python3-venv python3-pip` (Debian/Ubuntu) or your distro's equivalent | Any terminal |

Other install guides: [Python setup and usage](https://docs.python.org/3/using/index.html), [git](https://git-scm.com/downloads) (optional, only to clone agent0 for reference).

## Project setup

A virtual environment keeps this project's packages separate from the rest of your system. Create one per project:

```bash
mkdir my-agent && cd my-agent
python3 -m venv venv
```

Activate it (do this in every new terminal):

| Shell | Command |
|---|---|
| bash / zsh (Linux, macOS) | `source venv/bin/activate` |
| fish | `source venv/bin/activate.fish` |
| Windows PowerShell | `venv\Scripts\Activate.ps1` |
| Windows cmd | `venv\Scripts\activate.bat` |

Your prompt then starts with `(venv)`. On Windows PowerShell, if activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

```bash
pip install requests fastapi uvicorn
```

Next: [Step 1, install a local model](01-install-ollama.md).
