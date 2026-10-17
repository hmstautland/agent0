import os
import re
from ics import Calendar, Event
from datetime import date, datetime, time, timedelta

CALENDAR_FILE = "local_storage/my_calendar.ics"

CREATE_TRIGGER_RE = re.compile(
    r"\b(add|schedule|create|book|set(?: ?up)?|plan)\b.*\b(meeting|event|appointment|call|sync|reminder)\b",
    re.I,
)

# One clock time: "1030", "12.30", "12:30", "14", "2pm", "2.30 pm"
_TIME = r"\d{3,4}(?![:\d]|\.\d)|\d{1,2}(?:[:.]\d{2})?(?:\s*(?:am|pm))?"

# "at 12.30", "from 11 to 1", "at 2pm until 3", "from 9-10" - anywhere in the request
CREATE_TIME_RE = re.compile(
    rf"\b(?:at|from|ad)\s+(?P<start>{_TIME})(?:\s*(?:to|until|till|-)\s*(?P<end>{_TIME}))?(?![\w:]|\.\d)",
    re.I,
)

TITLE_KEYWORDS = ["meeting", "event", "appointment", "call", "sync", "reminder"]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Date-only formats for the "on <date>" part of a create command. Formats
# without a year are tried with the current year appended, so 29 February
# parses in a leap year.
DATE_FORMATS_WITH_YEAR = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
    "%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y",
]
DATE_FORMATS_WITHOUT_YEAR = ["%d %B", "%B %d", "%d %b", "%b %d", "%d/%m", "%d.%m"]


class CalendarCommandError(ValueError):
    """A request that is clearly an "add a meeting ..." command but can't be
    created as stated. The message is the reply shown to the user."""

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

def _parse_time_token(token):
    """(hour, minute, meridiem) for a 24-hour or am/pm clock time; meridiem is None without am/pm."""
    text = re.sub(r"\s+", "", token.lower())
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?(am|pm)?", text) or re.fullmatch(r"(\d{1,2})(\d{2})(am|pm)?", text)
    if not m:
        raise CalendarCommandError(f"I couldn't read the time '{token.strip()}'. Try for example 14:00, 14.00 or 2pm.")

    hour, minute, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3)

    if meridiem:
        if not 1 <= hour <= 12:
            raise CalendarCommandError(f"'{token.strip()}' isn't a valid time.")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)

    if hour > 23 or minute > 59:
        raise CalendarCommandError(f"'{token.strip()}' isn't a valid time.")

    return hour, minute, meridiem


def _resolve_times(day, start_token, end_token):
    """Start and end datetimes on day, following a 24-hour day.

    An end that comes out at or before the start is read as the afternoon
    when it has no am/pm ("11 to 1" -> 11:00-13:00, "2pm to 3" -> 14:00-15:00);
    if it is still earlier, it is on the next day ("23 to 1" -> 01:00 next day).
    """
    start_hour, start_minute, start_meridiem = _parse_time_token(start_token)
    if end_token is None:
        return datetime.combine(day, time(start_hour, start_minute)), None

    end_hour, end_minute, end_meridiem = _parse_time_token(end_token)

    # "3 to 4pm": the end's pm carries over to a start written without am/pm
    if start_meridiem is None and end_meridiem == "pm" and start_hour < 12 and start_hour + 12 < end_hour:
        start_hour += 12

    start = datetime.combine(day, time(start_hour, start_minute))
    end = datetime.combine(day, time(end_hour, end_minute))

    if end <= start and end_meridiem is None and end_hour < 12 and end + timedelta(hours=12) > start:
        end += timedelta(hours=12)
    if end <= start:
        end += timedelta(days=1)

    return start, end


def _normalize_date_text(text):
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text, flags=re.I)
    text = re.sub(r"\b(of|the)\b", " ", text, flags=re.I)
    text = text.replace(",", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_date_text(text, today):
    """(date, year_given) for "4 october", "october 4 2027", "2026-10-04", "4.10" ..., or None."""
    for fmt in DATE_FORMATS_WITH_YEAR:
        try:
            return datetime.strptime(text, fmt).date(), True
        except ValueError:
            pass

    for fmt in DATE_FORMATS_WITHOUT_YEAR:
        try:
            return datetime.strptime(f"{text} {today.year}", f"{fmt} %Y").date(), False
        except ValueError:
            pass

    return None


def _parse_day(text, today):
    """The day a create command is for: (date, year_given), or None if it names no day.

    Raises CalendarCommandError when "on <something>" is there but unreadable.
    """
    lower = text.lower()

    if re.search(r"\bday after tomorrow\b", lower):
        return today + timedelta(days=2), True
    if re.search(r"\btomorrow\b", lower):
        return today + timedelta(days=1), True
    if re.search(r"\b(today|tonight)\b", lower):
        return today, True

    m = re.search(rf"\b(next\s+|on\s+|this\s+)?({'|'.join(WEEKDAYS)})\b", lower)
    if m:
        days_ahead = (WEEKDAYS.index(m.group(2)) - today.weekday()) % 7
        if days_ahead == 0 and (m.group(1) or "").strip() == "next":
            days_ahead = 7
        return today + timedelta(days=days_ahead), True

    m = re.search(r"\bon\s+(?P<date>.+)$", text, re.I)
    if not m:
        return None

    # Whatever follows the date ("on 4 october with Bob") is not part of it:
    # use the longest leading run of words that parses as a date.
    words = _normalize_date_text(m.group("date")).split(" ")
    for count in range(min(len(words), 4), 0, -1):
        parsed = _parse_date_text(" ".join(words[:count]), today)
        if parsed:
            return parsed

    raise CalendarCommandError(
        f"I couldn't read the date '{m.group('date').strip()}'. "
        "Try for example 'on 4 october', 'on 2026-10-04' or 'tomorrow'."
    )


def parse_create_command(text, today=None):
    """Parse a natural-language "add a meeting tomorrow from 11 to 1" command.

    Returns create_event() kwargs ({"title", "start", "end"}), or None if the
    text isn't a calendar-creation request with a time. Raises
    CalendarCommandError when it is one but can't be created as stated
    (unreadable time/date, no day given, or a past date without a year).
    """
    if not text or not CREATE_TRIGGER_RE.search(text):
        return None

    time_match = CREATE_TIME_RE.search(text)
    if not time_match:
        return None

    today = today or date.today()

    title = "Meeting"
    for keyword in TITLE_KEYWORDS:
        if re.search(rf"\b{keyword}\b", text, re.I):
            title = keyword.capitalize()
            break

    without_time = (text[:time_match.start()] + " " + text[time_match.end():]).strip()
    day = _parse_day(without_time, today)
    if day is None:
        raise CalendarCommandError(f"Which day should the {title.lower()} be on? For example 'tomorrow' or 'on 4 october'.")

    day, year_given = day
    if not year_given and day < today:
        try:
            suggestion = day.replace(year=today.year + 1)
        except ValueError:  # 29 February
            suggestion = None
        hint = f" Did you mean {suggestion.day} {suggestion:%B %Y}?" if suggestion else ""
        raise CalendarCommandError(
            f"{day.day} {day:%B %Y} has already passed.{hint} "
            "Please say the date again with the year, for example 'on 5 january 2027'."
        )

    start, end = _resolve_times(day, time_match.group("start"), time_match.group("end"))
    return {"title": title, "start": start, "end": end or start + timedelta(hours=1)}


def calendar_view_for(start):
    """The show_calendar payload that opens start's month with its day highlighted, or None."""
    try:
        start = _parse_datetime(start)
    except ValueError:
        return None
    return {"year": start.year, "month": start.month, "day": start.day}


def _describe_event(title, start, end):
    when = f"{start:%A} {start.day} {start:%B %Y}, {start:%H:%M}-{end:%H:%M}"
    if end.date() != start.date():
        when += f" (ends {end:%A} {end.day} {end:%B})"
    return f"Added '{title}' on {when}."


def create_event_from_command(text, today=None):
    """Handle an "add a meeting ..." chat message without the LLM.

    Returns None if text isn't one. Otherwise a final_response-style dict:
    {"response": text} when it can't be created as stated (the reply asks
    the user to restate), or {"response", "show_calendar"} after creating
    it, so the UI opens the month with the new event's day highlighted.
    """
    try:
        command = parse_create_command(text, today=today)
    except CalendarCommandError as e:
        return {"response": str(e)}

    if command is None:
        return None

    try:
        create_event(**command)
    except ValueError as e:
        return {"response": f"I couldn't add the event: {e}"}

    return {
        "response": _describe_event(command["title"], command["start"], command["end"]),
        "show_calendar": calendar_view_for(command["start"]),
    }

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
