# ex: 
# create_event("Meeting", "2026-04-25 14:00")
import re
from ics import Calendar, Event
from datetime import datetime, timedelta

CALENDAR_FILE = "local_storage/my_calendar.ics"

def _parse_datetime(value):
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        raise ValueError("Empty date value")

    text = text.replace(" of ", " ")
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)

    current_year = datetime.now().year

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%d %B %Y %H:%M",
        "%d %B %Y",
        "%B %d %Y %H:%M",
        "%B %d %Y",
        "%d %b %Y %H:%M",
        "%d %b %Y",
        "%d %B %H:%M",
        "%B %d %H:%M",
        "%d %b %H:%M",
        "%b %d %H:%M",
        "%d %B",
        "%B %d",
        "%d %b",
        "%b %d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=current_year)
            return dt
        except Exception:
            pass

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    raise ValueError(f"Unable to parse date/time: {value}")

def _load_calendar():
    try:
        with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return Calendar()

    try:
        return Calendar(text)
    except Exception as e:
        if "Multiple calendars in one file" in str(e):
            calendars = Calendar.parse_multiple(text)
            merged = Calendar()
            for cal in calendars:
                merged.events.update(cal.events)
            return merged
        raise


def create_event(title, start, end=None, description=None):
    calendar = _load_calendar()

    if title is None:
        title = "Appointment"

    event = Event()
    event.name = title
    event.begin = _parse_datetime(start)

    if end:
        event.end = _parse_datetime(end)
    else:
        event.end = event.begin + timedelta(hours=1)

    event.description = description or f"Created by AI agent on {datetime.now()}"

    calendar.events.add(event)

    with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
        f.writelines(calendar)

    return f"Event '{title}' added from {event.begin} to {event.end}"

def read_calendar():
    calendar = _load_calendar()

    if not calendar.events:
        return "No events found."

    events = []
    for event in sorted(calendar.events, key=lambda e: e.begin):
        events.append({
            "name": event.name,
            "date": event.begin,
            "end": event.end,
            "description": event.description
        })

    return events