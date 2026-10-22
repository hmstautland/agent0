---
name: decision-log
description: Record an important decision in docs/DECISIONS.md when the user chooses between options that had pros and cons, or asks to log, record or write down a decision
---

Only log real trade-offs: two or more options were weighed and one was chosen.
Do not log cosmetic choices (colors, names, wording, formatting) or choices with only
one sensible answer. If the decision is still open, do not log it yet.

1. Call read_files with path docs/DECISIONS.md to see the format and earlier entries.
2. Call edit_file on docs/DECISIONS.md with
   old_text: <!-- New decisions go directly below this line, newest first. -->
   new_text: that same line, a blank line, then the new entry.
3. Write the entry in the format shown at the top of the file. Use the current date.
   Take the options, pros, cons and reason from the conversation. Do not invent any;
   if the reason is unclear, ask the user instead of guessing.
4. If the decision replaces an earlier entry, also edit that entry's Status line to
   "Superseded by <date>: <title>".
5. In your final answer, give the title of the entry you added.
