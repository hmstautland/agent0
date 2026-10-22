---
name: weekly-report
description: Summarise the user's last 7 days (what was done and notes) when they ask for a weekly report, week summary or "what happened this week"
---

Build the report from the user's own data. Do not invent anything.

1. Call search_history with days=7 and limit=30 to see what was asked and done.
2. Call list_notes with limit=20; keep only notes saved in the last 7 days.
3. Reply in this format, leaving out any section that has nothing in it:

## Done this week
- one line per piece of work, grouped by topic (mention edited files by name)

## Notes
- one line per note

Keep it under 20 lines. If both sources are empty, say there is nothing to report.
