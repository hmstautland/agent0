---
name: decision-log
description: Add an entry to docs/DECISIONS.md right after an important design or architecture decision is settled in this repo, meaning two or more viable options were weighed with real pros and cons and one was chosen (by the user, or agreed with them). Also use when the user asks to log or record a decision. Skip cosmetic or trivial choices (colors, naming, wording, formatting), choices with only one sensible answer, and decisions that are still open.
---

# Decision log

`docs/DECISIONS.md` records why agent0 is the way it is, so later sessions don't re-argue settled choices and can tell when one is worth revisiting.

## When to log

Log a decision when all of these hold:
- At least two options were viable, and each had real pros and cons that were discussed.
- One was chosen, either by the user or agreed with them. Proposing an option yourself doesn't count until the user accepts it.
- It shapes how the code is built or used: architecture, dependencies, data formats, storage, security or permission rules, model choice, what is deliberately left out.

Don't log:
- Cosmetic choices: colors, names, wording, layout tweaks, formatting.
- Choices with only one sensible answer, or plain bug fixes.
- Decisions that are still open. Log them once they are settled.

If you're unsure whether it's important enough, ask the user in one line instead of logging it silently.

## How to log

1. Read `docs/DECISIONS.md` to see the format and the earlier entries. If an entry already covers this decision, update it instead of adding a duplicate.
2. Insert the new entry directly below the `<!-- New decisions go directly below this line, newest first. -->` marker, using the entry format at the top of the file. Use today's date.
3. Take the options, pros, cons and reason from the conversation. Don't invent pros and cons that weren't discussed. Name the files involved where that helps a later reader.
4. If the decision replaces an earlier entry, change that entry's status to `Superseded by <date>: <title>` and leave the entry in place.
5. Keep each entry short: a reader should get the gist in about 30 seconds.
6. Tell the user in one line that you logged it, with the entry title.

If the decision also changes how the code should be edited, update `CLAUDE.md` as well. The log records why the choice was made; `CLAUDE.md` says what to do because of it.
