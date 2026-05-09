# ex: 
# create_event("Meeting", "2026-04-25 14:00")
from ics import Calendar, Event
from datetime import datetime

CALENDAR_FILE = "projects/agent0/local_storage/my_calendar.ics"

def create_event(title, date):
    try:
        with open(CALENDAR_FILE, "r") as f:
            calendar = Calendar(f.read())
    except FileNotFoundError:
        calendar = Calendar()

    event = Event()
    event.name = title
    event.begin = date

    calendar.events.add(event)

    with open(CALENDAR_FILE, "w") as f:
        f.writelines(calendar)

    return f"Event '{title}' added on {date}";