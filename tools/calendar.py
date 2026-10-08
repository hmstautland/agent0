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


SHOW_CALENDAR_RE = re.compile(r"calendar", re.I)
SHOW_TRIGGER_WORDS = ("show", "my calendar", "what's on", "what is on")
MONTH_DAY_RE = re.compile(
    r"(\b\d{1,2}\b)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", re.I
)


def is_calendar_show_command(text):
    """Detect "show my calendar" / "what's on today" style requests."""
    lu = (text or "").lower()
    return bool(SHOW_CALENDAR_RE.search(lu)) and any(word in lu for word in SHOW_TRIGGER_WORDS)


def _event_date(event):
    d = event.get("date")
    if hasattr(d, "date") and callable(d.date):
        return d.date()
    if isinstance(d, datetime):
        return d.date()
    if hasattr(d, "naive"):
        try:
            return d.naive.date()
        except Exception:
            pass
    return None


def _to_plain_datetime(value):
    if hasattr(value, "naive"):
        try:
            return value.naive
        except Exception:
            pass
    if hasattr(value, "datetime"):
        try:
            return value.datetime
        except Exception:
            pass
    return value


def get_calendar_view(user_input):
    """Read the calendar and apply any date filter implied by user_input.

    Used for "show my calendar" style requests, which bypass the LLM. Handles
    "today" and a bare day+month (e.g. "17 may"), and normalizes event dates
    to plain datetimes for the template.
    """
    events = read_calendar()
    if not isinstance(events, list):
        events = []  # read_calendar() returns a string when empty

    lu = (user_input or "").lower()

    if "today" in lu:
        today = datetime.now().date()
        events = [e for e in events if _event_date(e) == today]

    m = MONTH_DAY_RE.search(lu)
    if m:
        day, month_str = m.group(1), m.group(2)
        try:
            target_date = _parse_datetime(f"{day} {month_str}").date()
            events = [e for e in events if _event_date(e) == target_date]
        except ValueError:
            pass

    for e in events:
        if "date" in e:
            e["date"] = _to_plain_datetime(e["date"])
        if "end" in e:
            e["end"] = _to_plain_datetime(e["end"])

    return events