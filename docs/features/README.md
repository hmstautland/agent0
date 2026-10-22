# Features

One page per feature: what it does, how to use it, its settings and its limits. The top-level [README](../../README.md) covers setup only. For how the code fits together, see [CLAUDE.md](../../CLAUDE.md). For why things are the way they are, see the [decision log](../DECISIONS.md).

| Feature | What it does |
| --- | --- |
| [Agent loop and models](agent-loop.md) | Direct answers first, then a multi-step tool loop on a local Ollama model; context pruning, the stop button |
| [Permissions and file safety](permissions.md) | Approval cards, per-tool rules, the project sandbox, automatic backups |
| [Conversation memory](conversation-memory.md) | Follow-up questions within a conversation, and searching earlier ones |
| [Skills](skills.md) | Markdown instructions the agent loads only when a task needs them |
| [Web search](web-search.md) | DuckDuckGo search, news headlines, reading pages |
| [Calendar](calendar.md) | Adding events from chat, and a month view |
| [Notes](notes.md) | Saving and listing notes by typing or speaking |
| [Speech-to-text](speech-to-text.md) | The mic button and the CLI's speak mode (faster-whisper) |
| [Text-to-speech](text-to-speech.md) | The Kokoro dashboard: voices, dialogue, documents, conversion |
| [Audio playback](audio-playback.md) | "play ..." to find and play saved audio |
| [Event log](event-log.md) | The JSONL log of everything the agent does |
| [Remote access](remote-access.md) | Using the web UI from other devices over Tailscale, and starting it on demand |

## Adding a page

Write one page for each new user-visible feature, and add a row for it to the table above. Use this layout and leave out any section that has nothing in it:

```
# Feature name

One or two sentences: what it does and who it's for.

## Using it
What the user types, clicks or says, with an example.

## How it works
A short description of the moving parts, naming the main files.

## Settings
Environment variables / config, as a table with defaults.

## Limits
What it doesn't do, and known trade-offs.
```
