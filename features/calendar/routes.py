"""HTTP surface of the calendar feature: the month-grid data endpoint and its
static assets (features/calendar/static, served at /static/calendar)."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.staticfiles import StaticFiles

from core.auth import is_logged_in
from features.calendar.calendar import month_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"

calendar_router = APIRouter(dependencies=[Depends(is_logged_in)])


@calendar_router.get("/calendar/month")
async def calendar_month(year: int = None, month: int = None):
    return month_payload(year, month)


def calendar_static_files():
    # Only the static/ subfolder is exposed, so calendar.py is never served.
    return StaticFiles(directory=str(STATIC_DIR))
