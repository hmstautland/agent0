# Diagrams

← [Back to the guide](../BUILD_YOUR_OWN_AGENT.md)

Both diagrams are [Mermaid](https://mermaid.js.org/), which GitHub, GitLab and most editors render directly. The first shows what happens when you talk to the agent; the second shows the parts and which one talks to which. They describe agent0, which is v1 plus the v2 add-ons. Parts marked *(v2)* can be left out of your first version.

## 1. Interaction flow: what happens to one message

```mermaid
flowchart TD
    U([You type or speak a message]) --> UI[Web UI or CLI]
    UI --> SC{"Shortcut match?<br/>calendar, play audio<br/>notes too, web UI only<br/>(v2)"}
    SC -- yes --> SCR[Plain code handles it<br/>no model involved]
    SC -- no --> RT{"Obviously needs tools?<br/>(file names, code)"}
    RT -- no --> LF["Local-first call:<br/>can the model answer directly?<br/>(v2)"]
    LF -- "yes" --> ANS
    LF -- "needs tools" --> LOOP
    RT -- yes --> LOOP

    subgraph LOOP [The agent loop, max N steps]
        direction TB
        M["Send system prompt + history + question<br/>to the model (Ollama)"] --> TC{Model asks<br/>for a tool?}
        TC -- yes --> PM{"Permission check<br/>low risk, or approved before?"}
        PM -- yes --> RUN[Run the tool function]
        PM -- no --> PARK["Pause and show an approval card<br/>(run is parked)"]
        PARK -- "you approve" --> RUN
        PARK -- "you deny" --> DEN["Tool result = ERROR: user denied"]
        RUN --> RES["Add the result to the messages<br/>(capped, old results pruned)"]
        DEN --> RES
        RES --> M
    end

    TC -- "no: plain text" --> ANS[Final answer]
    SCR --> ANS
    ANS --> SAVE["Save the turn to local storage<br/>and write log lines (v2)"]
    SAVE --> OUT([Answer shown in the UI, optionally read aloud])

    STOP([Stop button]) -. "cancels the model call" .-> M
```

Reading it:

- **The loop is the agent.** Everything above it is optional routing to save time or improve reliability; everything below it is storage and output.
- **Every tool call passes the permission check** before the function runs. A denial goes back to the model as text, so it can explain what it couldn't do instead of crashing.
- **A parked run is resumed, not restarted.** The approval card only sends the run's id and your decision; the loop continues from where it paused.
- **The first version (v1) is just:** message → loop → permission check → tools → answer. Add the other boxes one add-on at a time.

## 2. Architecture: the parts

```mermaid
flowchart LR
    subgraph IN [Input]
        WEB[Web UI<br/>FastAPI + HTML/JS]
        CLI[CLI]
        MIC["Mic<br/>faster-whisper (v2)"]
    end

    subgraph CORE [Agent core]
        AG[agent.py<br/>the loop]
        SP[System prompt<br/>+ skills index]
        PERM[Permissions<br/>risk levels + RULES]
        CTX["Context pruning<br/>(v2)"]
    end

    subgraph TOOLS [Tools: registry.py]
        FT[Files<br/>read, search, edit]
        WT[Web search]
        CT[Calendar, notes]
        SK[load_skill]
        SH[search_history]
    end

    subgraph DATA [Local storage]
        DB[("SQLite<br/>conversations + full-text search")]
        FS[Notes, audio, backups]
        LOG[logs.txt<br/>JSON lines]
        SKF[skills/*.md]
    end

    OLL[["Ollama server<br/>localhost:11434"]]
    MODEL[(Local model<br/>in RAM / GPU)]
    TTS["Speaker<br/>Kokoro TTS (v2)"]

    WEB --> AG
    CLI --> AG
    MIC --> WEB
    AG --> SP
    AG --> CTX
    AG <--> OLL
    OLL --- MODEL
    AG --> PERM
    PERM --> TOOLS
    FT --> FS
    CT --> FS
    SH --> DB
    SK --> SKF
    WT -. "only part that leaves the machine" .-> NET((Internet))
    AG --> DB
    AG --> LOG
    WEB --> TTS
```

Reading it:

- **Everything runs on your machine.** The only arrow that leaves it is web search, which is why those tools ask for approval once per session.
- **`agent.py` is the hub.** It builds the prompt, talks to Ollama, passes each tool call through permissions, and records the result.
- **Tools are plain functions** declared in one registry. Adding a capability means adding an entry there; nothing else in the core changes.
- **Ollama is a separate process.** Your code only knows its HTTP address, so you can swap the model, or move Ollama to another machine, by changing a URL or a model name.
- **Voice is UI, not agent.** The mic and speaker sit beside the web UI and bypass the loop; the agent only ever sees text.

| Box | agent0 file |
|---|---|
| Web UI, CLI | `core/ui.py`, `templates/`, `static/`, `agent.py` (`python -m agent`) |
| Agent loop | `agent.py` |
| System prompt, skills | `config/system_prompt.py`, `tools/skills.py`, `skills/` |
| Permissions | `core/permission.py`, `core/runs.py`, `config/settings.py` |
| Context pruning | `core/context.py` |
| Tools | `tools/registry.py`, `tools/*.py`, `features/` |
| Model client | `core/llm.py` |
| Storage, history | `storage/`, `core/conversations.py` |
| Logger | `core/logger.py` |
| Mic, speaker | `core/speech_to_text.py`, `features/audio/` |
