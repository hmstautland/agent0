import os
import re
from ics import Calendar, Event
from datetime import datetime, timedelta

CALENDAR_FILE = "local_storage/my_calendar.ics"

CREATE_TRIGGER_RE = re.compile(
    r"\b(add|schedule|create|book|set ?up)\b.*\b(meeting|event|appointment|call|sync|reminder)\b",
    re.I,
)

# "on 4th october at 12 to 14" / "on 4th october from 12:00 until 14:00"
CREATE_RANGE_RE = re.compile(
    r"\bon\s+(?P<date>.+?)\s+(?:at|from|ad)\s+(?P<start>[\d:apm. ]+?)\s*(?:to|until|-)\s*(?P<end>[\d:apm. ]+)$",
    re.I,
)

# "on 4th october at 12:00" (no end time given)
CREATE_SINGLE_RE = re.compile(
    r"\bon\s+(?P<date>.+?)\s+(?:at|from|ad)\s+(?P<start>[\d:apm. ]+)$",
    re.I,
)

TITLE_KEYWORDS = ["meeting", "event", "appointment", "call", "sync", "reminder"]

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

def _normalize_time_token(token):
    token = token.strip().lower().replace(".", "")
    m = re.match(r"^(\d{1,2})(:(\d{2}))?\s*(am|pm)?$", token)
    if not m:
        return token

    hour = int(m.group(1))
    minute = m.group(3) or "00"
    ampm = m.group(4)

    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute}"

def parse_create_command(text):
    """Best-effort parse of a natural-language "add a meeting on ..." command.

    Returns a dict of create_event() kwargs, or None if the text doesn't
    look like a calendar-creation request.
    """
    if not text or not CREATE_TRIGGER_RE.search(text):
        return None

    title = "Meeting"
    for keyword in TITLE_KEYWORDS:
        if re.search(rf"\b{keyword}\b", text, re.I):
            title = keyword.capitalize()
            break

    m = CREATE_RANGE_RE.search(text)
    if m:
        date_part = m.group("date").strip()
        start_token = _normalize_time_token(m.group("start"))
        end_token = _normalize_time_token(m.group("end"))
        try:
            return {
                "title": title,
                "start": _parse_datetime(f"{date_part} {start_token}"),
                "end": _parse_datetime(f"{date_part} {end_token}"),
            }
        except ValueError:
            return None

    m = CREATE_SINGLE_RE.search(text)
    if m:
        date_part = m.group("date").strip()
        start_token = _normalize_time_token(m.group("start"))
        try:
            return {
                "title": title,
                "start": _parse_datetime(f"{date_part} {start_token}"),
            }
        except ValueError:
            return None

    return None

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

    os.makedirs(os.path.dirname(CALENDAR_FILE), exist_ok=True)
    with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
        f.writelines(calendar.serialize_iter())

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


def is_calendar_event_list(value):
    """True if value looks like read_calendar()'s event-list return shape.

    Used to recognize a read_calendar tool result regardless of which code
    path produced it (the chat shortcut, or the LLM choosing the tool
    itself), so it can be shown as the month-grid calendar instead of being
    flattened into a text summary.
    """
    return (
        isinstance(value, list)
        and bool(value)
        and isinstance(value[0], dict)
        and "date" in value[0]
        and "end" in value[0]
    )


def events_in_month(year, month):
    """Events whose start falls in the given (year, month), always a list.

    Unlike read_calendar(), this never returns the "No events found." string
    sentinel - callers (the month-grid calendar view) just want an empty
    list to render a blank month.
    """
    calendar = _load_calendar()

    events = []
    for event in sorted(calendar.events, key=lambda e: e.begin):
        if event.begin.year == year and event.begin.month == month:
            events.append({
                "name": event.name,
                "date": event.begin,
                "end": event.end,
                "description": event.description
            })

    return events


def event_iso(value):
    """Normalize an ics Arrow (or plain datetime) into an ISO string for JSON."""
    if hasattr(value, "naive"):
        try:
            return value.naive.isoformat()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def month_payload(year=None, month=None):
    """JSON-ready events for GET /calendar/month; defaults to the current month."""
    now = datetime.now()
    year = year or now.year
    month = month if month and 1 <= month <= 12 else now.month

    return {
        "year": year,
        "month": month,
        "events": [
            {
                "name": e["name"],
                "start": event_iso(e["date"]),
                "end": event_iso(e["end"]),
                "description": e["description"],
            }
            for e in events_in_month(year, month)
        ],
    }


def is_calendar_request(user_input):
    """True for "show my calendar" / "what's on" style chat messages."""
    lu = (user_input or "").lower()
    return "calendar" in lu and (
        "show" in lu or "my calendar" in lu or "what's on" in lu or "what is on" in lu
    )


def calendar_target_month(user_input):
    """Pick which (year, month) a "show my calendar" chat message means.

    Defaults to the current month; a mentioned day+month (e.g. "17 may")
    opens whichever month contains that date instead.
    """
    target = datetime.now()

    m = re.search(
        r"(\b\d{1,2}\b)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*",
        (user_input or "").lower(),
    )
    if m:
        try:
            target = _parse_datetime(f"{m.group(1)} {m.group(2)}")
        except Exception:
            pass

    return target.year, target.month
