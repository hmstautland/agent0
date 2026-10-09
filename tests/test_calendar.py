from datetime import datetime

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
