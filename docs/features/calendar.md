# Calendar

A local calendar: add events from chat and see them in a month view.

## Using it

- **Add an event:** "add a meeting with Ola on 17 May at 14 until 15", "schedule a call tomorrow at 2pm". A clear "add/schedule/book ... meeting/event/call ..." request is handled directly without the model, and without an approval card, since you typed it yourself. If the time or date can't be understood, you're asked to restate it.
- **Show the calendar:** "show my calendar", "what's on my calendar". Mention a date ("show my calendar for 17 May") to open that month. The month grid highlights a newly added event's day.
- The model can also use the calendar itself: `read_calendar` (no approval) and `create_calendar_event` (asks first).

## How it works

Everything lives in `features/calendar/`. `calendar.py` holds the events, command parsing and month data; `routes.py` serves `GET /calendar/month`; `static/` is the month-grid UI. Events are stored in `local_storage/my_calendar.ics`.

Accepted formats: dates like `on 2026-05-17`, `on 17/05`, `on 17 May`, `on May 17`, weekdays (`next friday`), `today`, `tomorrow`, `day after tomorrow`; times like `14`, `1030`, `12:30`, `12.30`, `2pm`, with an optional end time (`to`, `until`, `-`).

## Limits

- It's a single local `.ics` file, with no sync to Google, Outlook or other calendars.
- Events can't be edited or deleted from chat.
