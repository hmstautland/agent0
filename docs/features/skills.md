# Skills

Skills are step-by-step instructions for one kind of task, written as markdown files in `skills/`. The agent loads one only when a request needs it, so unused skills cost no context.

## Using it

Ask for something a skill covers, such as "give me a weekly report", and the model loads that skill and follows it.

Shipped skills:

| Skill | What it does |
| --- | --- |
| `weekly-report` | Summarises the last 7 days from conversation history and notes |
| `move-code-out-of-file` | Rules for moving code into another file without losing it |
| `decision-log` | Adds an entry to [docs/DECISIONS.md](../DECISIONS.md) |
| `document-feature` | Offers to document a new feature in this folder |

## How it works

The system prompt gets only a one-line index: each skill's name and when to use it. The model calls the low-risk `load_skill` tool to fetch the full text. Code: `tools/skills.py`.

To add a skill, drop a file in `skills/`:

```
---
name: my-skill
description: when the model should use it
---

The instructions.
```

## Limits

- The local model decides whether a request matches a skill, so a vague description means it won't get loaded.
- Even with a matching description, a model may skip `load_skill` (the code model did in testing for `move-code-out-of-file`). Keep rules that protect data in the system prompt, and use skills for how-to detail.
- A skill can't rely on `read_calendar`: that tool ends the run by opening the calendar grid, so the model never sees the events.
