import json
from datetime import date, datetime, timedelta

import pytest

import core.auth as auth_mod
import core.ui as ui_mod
import features.calendar.calendar as calendar_mod
from fastapi.testclient import TestClient


def _logged_in_client(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    client = TestClient(ui_mod.app)
    client.post("/login", data={"password": "testpass"})
    return client


def _use_temp_calendar(monkeypatch, tmp_path):
    """Point features.calendar.calendar at a throwaway .ics file for this test."""
    calendar_file = tmp_path / "calendar.ics"
    monkeypatch.setattr(calendar_mod, "CALENDAR_FILE", str(calendar_file))
    return calendar_file


# --- features.calendar.calendar.events_in_month -----------------------------

def test_events_in_month_filters_to_the_given_year_and_month(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)

    calendar_mod.create_event("May event", "2026-05-17 10:00", "2026-05-17 11:00")
    calendar_mod.create_event("June event", "2026-06-01 09:00", "2026-06-01 10:00")

    may_events = calendar_mod.events_in_month(2026, 5)

    assert [e["name"] for e in may_events] == ["May event"]


def test_events_in_month_returns_empty_list_not_a_sentinel_string(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)

    assert calendar_mod.events_in_month(2026, 5) == []


def test_events_in_month_sorts_by_start_time(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)

    calendar_mod.create_event("Later", "2026-05-20 10:00", "2026-05-20 11:00")
    calendar_mod.create_event("Earlier", "2026-05-05 10:00", "2026-05-05 11:00")

    names = [e["name"] for e in calendar_mod.events_in_month(2026, 5)]

    assert names == ["Earlier", "Later"]


# --- features.calendar.calendar helpers ---------------------------------------------------------

def test_is_calendar_request_matches_expected_phrasings():
    assert calendar_mod.is_calendar_request("can I view my calendar")
    assert calendar_mod.is_calendar_request("show calendar please")
    assert calendar_mod.is_calendar_request("what's on my calendar today")
    assert not calendar_mod.is_calendar_request("what's the weather today")


def test_calendar_target_month_defaults_to_current_month():
    now = datetime.now()
    assert calendar_mod.calendar_target_month("show my calendar") == (now.year, now.month)


def test_calendar_target_month_uses_a_mentioned_day_and_month():
    year, month = calendar_mod.calendar_target_month("what's on 17 may")
    assert month == 5


# --- GET /calendar/month -----------------------------------------------------

def test_calendar_month_route_returns_events_with_iso_dates(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)
    calendar_mod.create_event("Meeting", "2026-05-17 10:00", "2026-05-17 11:00", "Weekly sync")

    client = _logged_in_client(monkeypatch)
    response = client.get("/calendar/month", params={"year": 2026, "month": 5})

    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2026
    assert data["month"] == 5
    assert len(data["events"]) == 1
    event = data["events"][0]
    assert event["name"] == "Meeting"
    assert event["description"] == "Weekly sync"
    assert event["start"].startswith("2026-05-17T10:00")
    assert event["end"].startswith("2026-05-17T11:00")


def test_calendar_month_route_defaults_to_current_month(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)

    client = _logged_in_client(monkeypatch)
    response = client.get("/calendar/month")

    now = datetime.now()
    data = response.json()
    assert (data["year"], data["month"]) == (now.year, now.month)
    assert data["events"] == []


def test_calendar_month_route_requires_authentication():
    client = TestClient(ui_mod.app)

    response = client.get("/calendar/month", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_ask_calendar_shortcut_opens_the_month_grid(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)
    client = _logged_in_client(monkeypatch)

    response = client.post("/ask", data={"input": "can I view my calendar"})

    assert response.status_code == 200
    assert 'id="calendar-card"' in response.text
    now = datetime.now()
    assert f'data-initial-year="{now.year}" data-initial-month="{now.month}"' in response.text


def test_ask_stream_calendar_shortcut_emits_show_calendar_event(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)
    client = _logged_in_client(monkeypatch)

    response = client.post("/ask_stream", data={"input": "show my calendar"})

    assert response.status_code == 200
    now = datetime.now()
    event = response.json()
    assert event["event"] == "final_response"
    assert event["show_calendar"] == {"year": now.year, "month": now.month}


# --- "add a meeting ..." chat command parsing ---------------------------------

TODAY = date(2026, 10, 17)  # a Saturday


def _times(text, today=TODAY):
    command = calendar_mod.parse_create_command(text, today=today)
    return command["start"], command["end"]


@pytest.mark.parametrize("phrase, start, end", [
    # The year-1230 bug: dotted, compact and am/pm times
    ("add a meeting on 20 october at 12.30", (20, 12, 30), (20, 13, 30)),
    ("add a meeting on 20 october at 14.00", (20, 14, 0), (20, 15, 0)),
    ("add a meeting on 20 october at 1030", (20, 10, 30), (20, 11, 30)),
    ("add a meeting on 20 october at 2.30 pm", (20, 14, 30), (20, 15, 30)),
    ("add a meeting tomorrow at 12.30.", (18, 12, 30), (18, 13, 30)),
    # Ranges follow a 24-hour day: an earlier end is read as the afternoon, then as the next day
    ("set a meeting from 11 to 1 tomorrow", (18, 11, 0), (18, 13, 0)),
    ("add a meeting on 20 october at 2pm to 3", (20, 14, 0), (20, 15, 0)),
    ("add a meeting on 20 october at 3 to 4pm", (20, 15, 0), (20, 16, 0)),
    ("add a meeting on 20 october from 23 to 1", (20, 23, 0), (21, 1, 0)),
    ("add a meeting on 20 october at 14 to 12", (20, 14, 0), (21, 12, 0)),
    ("schedule a call on friday at 9", (23, 9, 0), (23, 10, 0)),
    ("add a meeting on 4th of november at 10", (4, 10, 0), (4, 11, 0)),
])
def test_parse_create_command_times_and_ranges(phrase, start, end):
    got_start, got_end = _times(phrase)

    assert (got_start.day, got_start.hour, got_start.minute) == start
    assert (got_end.day, got_end.hour, got_end.minute) == end
    assert got_start.year == 2026


def test_a_past_date_without_a_year_asks_which_year():
    with pytest.raises(calendar_mod.CalendarCommandError, match="5 January 2026 has already passed.*5 January 2027"):
        calendar_mod.parse_create_command("add a meeting on 5 january at 10", today=TODAY)

    start, _ = _times("add a meeting on 5 january 2027 at 10")
    assert start.year == 2027


def test_29_february_parses_in_a_leap_year():
    start, _ = _times("add a meeting on 29 february at 9", today=date(2028, 1, 10))
    assert (start.year, start.month, start.day) == (2028, 2, 29)


@pytest.mark.parametrize("phrase, message", [
    ("add a meeting at 3", "Which day"),
    ("add a meeting on zoom at 3", "couldn't read the date"),
    ("add a meeting tomorrow at 25", "isn't a valid time"),
])
def test_create_commands_that_cannot_be_created_as_stated_explain_why(phrase, message):
    with pytest.raises(calendar_mod.CalendarCommandError, match=message):
        calendar_mod.parse_create_command(phrase, today=TODAY)


def test_text_without_a_create_trigger_or_a_time_is_not_a_create_command():
    assert calendar_mod.parse_create_command("when is the meeting", today=TODAY) is None
    assert calendar_mod.parse_create_command("schedule a team sync", today=TODAY) is None


def test_create_event_from_command_creates_and_returns_the_calendar_view(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)

    result = calendar_mod.create_event_from_command("set a meeting from 11 to 1 tomorrow", today=TODAY)

    assert result == {
        "response": "Added 'Meeting' on Sunday 18 October 2026, 11:00-13:00.",
        "show_calendar": {"year": 2026, "month": 10, "day": 18},
    }
    assert [e["name"] for e in calendar_mod.events_in_month(2026, 10)] == ["Meeting"]


def test_create_event_from_command_writes_nothing_when_it_has_to_ask(monkeypatch, tmp_path):
    calendar_file = _use_temp_calendar(monkeypatch, tmp_path)

    result = calendar_mod.create_event_from_command("add a meeting on 5 january at 10", today=TODAY)

    assert "already passed" in result["response"] and "show_calendar" not in result
    assert not calendar_file.exists()


def test_ask_stream_create_command_opens_the_calendar_on_the_new_event(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)
    client = _logged_in_client(monkeypatch)

    response = client.post("/ask_stream", data={"input": "add a meeting tomorrow at 2pm to 3"})
    event = json.loads(response.text.strip())

    tomorrow = date.today() + timedelta(days=1)
    assert event["event"] == "final_response"
    assert event["show_calendar"] == {"year": tomorrow.year, "month": tomorrow.month, "day": tomorrow.day}
    assert "14:00-15:00" in event["response"]


def test_ask_create_command_renders_the_calendar_with_the_day_highlighted(monkeypatch, tmp_path):
    _use_temp_calendar(monkeypatch, tmp_path)
    client = _logged_in_client(monkeypatch)

    response = client.post("/ask", data={"input": "add a meeting tomorrow at 9"})

    tomorrow = date.today() + timedelta(days=1)
    assert f'data-initial-day="{tomorrow.day}"' in response.text
