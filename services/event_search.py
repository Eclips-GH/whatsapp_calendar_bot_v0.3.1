import os
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from calendars.apple_calendar import apple_is_configured, list_apple_events
from calendars.google_calendar import google_is_configured, list_google_events

TZ = ZoneInfo("Europe/Zurich")
SEARCH_PAST_DAYS = int(os.getenv("EVENT_SEARCH_PAST_DAYS", "30"))
SEARCH_FUTURE_DAYS = int(os.getenv("EVENT_SEARCH_FUTURE_DAYS", "365"))


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.casefold().split())


def _day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=TZ)
    return start, start + timedelta(days=1)


def find_events(
    query: str,
    *,
    event_date: date | None = None,
    provider: str | None = None,
    calendar_name: str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    query_norm = normalize(query)
    if not query_norm:
        raise ValueError("Précise le nom de l'événement à rechercher.")

    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)

    if event_date:
        start, end = _day_range(event_date)
    else:
        start = now - timedelta(days=SEARCH_PAST_DAYS)
        end = now + timedelta(days=SEARCH_FUTURE_DAYS)

    events = []

    if provider in {None, "google"} and google_is_configured():
        events.extend(list_google_events(start, end))

    if provider in {None, "apple"} and apple_is_configured():
        events.extend(list_apple_events(start, end))

    if calendar_name:
        wanted_calendar = normalize(calendar_name)
        events = [
            event
            for event in events
            if normalize(event.get("calendar_name", "")) == wanted_calendar
        ]

    exact = [event for event in events if normalize(event.get("title", "")) == query_norm]
    matches = exact or [
        event
        for event in events
        if query_norm in normalize(event.get("title", ""))
    ]

    return sorted(matches, key=lambda event: event.get("sort") or event["start"])


def serializable_event_ref(event: dict) -> dict:
    return {
        "provider": event.get("provider"),
        "id": event.get("id", ""),
        "calendar_id": event.get("calendar_id"),
        "calendar_name": event.get("calendar_name", ""),
        "title": event.get("title", "(Sans titre)"),
        "start": event["start"].isoformat(),
        "end": event.get("end").isoformat() if event.get("end") else None,
        "all_day": bool(event.get("all_day")),
        "recurring": bool(event.get("recurring")),
        "source": event.get("source", ""),
        "resource_url": event.get("resource_url", ""),
        "etag": event.get("etag"),
    }


def deserialize_event_ref(data: dict) -> dict:
    start = datetime.fromisoformat(data["start"])
    end_text = data.get("end")
    end = datetime.fromisoformat(end_text) if end_text else None

    if start.tzinfo is None:
        start = start.replace(tzinfo=TZ)
    else:
        start = start.astimezone(TZ)

    if end:
        if end.tzinfo is None:
            end = end.replace(tzinfo=TZ)
        else:
            end = end.astimezone(TZ)

    result = dict(data)
    result["start"] = start
    result["end"] = end
    result["sort"] = start
    return result
