import os
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

TZ = ZoneInfo("Europe/Zurich")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = Path(os.getenv("GOOGLE_TOKEN_FILE", "token.json"))
WRITABLE_ACCESS_ROLES = {"owner", "writer"}


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.casefold().split())


def google_is_configured() -> bool:
    return TOKEN_FILE.exists()


def _service():
    if not TOKEN_FILE.exists():
        raise RuntimeError(f"Token Google introuvable : {TOKEN_FILE}")

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    if not creds.valid:
        raise RuntimeError("Authentification Google invalide")

    return build("calendar", "v3", credentials=creds)


def _get_all_calendars(service) -> list[dict]:
    calendars = []
    page_token = None

    while True:
        result = service.calendarList().list(pageToken=page_token).execute()
        calendars.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return calendars


def _calendar_by_id(service, calendar_id: str) -> dict:
    return service.calendarList().get(calendarId=calendar_id).execute()


def _assert_writable(calendar: dict) -> None:
    if calendar.get("accessRole") not in WRITABLE_ACCESS_ROLES:
        name = calendar.get("summary", calendar.get("id", "Sans nom"))
        raise PermissionError(f"Le calendrier Google '{name}' est en lecture seule.")


def list_google_calendars() -> list[str]:
    service = _service()
    return [
        calendar.get("summary", calendar.get("id", "Sans nom"))
        for calendar in _get_all_calendars(service)
    ]


def list_google_writable_calendars() -> list[str]:
    service = _service()
    return [
        calendar.get("summary", calendar.get("id", "Sans nom"))
        for calendar in _get_all_calendars(service)
        if calendar.get("accessRole") in WRITABLE_ACCESS_ROLES
    ]


def _find_google_calendar(service, calendar_name: str) -> dict:
    wanted = _normalize_name(calendar_name)
    calendars = _get_all_calendars(service)
    matches = [
        calendar
        for calendar in calendars
        if _normalize_name(calendar.get("summary", "")) == wanted
    ]

    if not matches:
        available = ", ".join(
            calendar.get("summary", calendar.get("id", "Sans nom"))
            for calendar in calendars
        )
        raise ValueError(
            f"Calendrier Google '{calendar_name}' introuvable. Disponibles : {available}"
        )

    if len(matches) > 1:
        raise ValueError(
            f"Plusieurs calendriers Google portent le nom '{calendar_name}'. "
            "Renomme-en un pour éviter l'ambiguïté."
        )

    return matches[0]


def _parse_google_datetime(data: dict, fallback: datetime | None = None):
    if "dateTime" in data:
        dt = datetime.fromisoformat(data["dateTime"].replace("Z", "+00:00"))
        return dt.astimezone(TZ), False

    if "date" in data:
        day = datetime.fromisoformat(data["date"]).date()
        return datetime(day.year, day.month, day.day, tzinfo=TZ), True

    if fallback is not None:
        return fallback, False

    return datetime.max.replace(tzinfo=TZ), False


def _event_to_dict(event: dict, calendar: dict) -> dict:
    calendar_id = calendar["id"]
    calendar_name = calendar.get("summary", calendar_id)
    start_dt, all_day = _parse_google_datetime(event.get("start", {}))

    default_end = start_dt + (timedelta(days=1) if all_day else timedelta(hours=1))
    end_dt, _ = _parse_google_datetime(event.get("end", {}), fallback=default_end)

    return {
        "title": event.get("summary", "(Sans titre)"),
        "start": start_dt,
        "end": end_dt,
        "sort": start_dt,
        "all_day": all_day,
        "source": f"Google • {calendar_name}",
        "provider": "google",
        "calendar_id": calendar_id,
        "calendar_name": calendar_name,
        "id": event.get("id"),
        "recurring": bool(event.get("recurringEventId") or event.get("recurrence")),
    }


def _events_from_calendar(service, calendar: dict, start: datetime, end: datetime) -> list[dict]:
    events = []
    page_token = None

    while True:
        result = (
            service.events()
            .list(
                calendarId=calendar["id"],
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )

        for event in result.get("items", []):
            if event.get("status") != "cancelled":
                events.append(_event_to_dict(event, calendar))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return events


def list_google_events(start: datetime, end: datetime) -> list[dict]:
    service = _service()
    events = []

    for calendar in _get_all_calendars(service):
        try:
            events.extend(_events_from_calendar(service, calendar, start, end))
        except Exception as exc:
            calendar_name = calendar.get("summary", calendar.get("id", "inconnu"))
            print(f"Erreur calendrier Google '{calendar_name}' : {exc}")

    return events


def create_google_event(title: str, start: datetime, end: datetime, calendar_name: str) -> dict:
    if end <= start:
        raise ValueError("L'heure de fin doit être après l'heure de début.")

    service = _service()
    calendar = _find_google_calendar(service, calendar_name)
    _assert_writable(calendar)

    body = {
        "summary": title,
        "start": {"dateTime": start.astimezone(TZ).isoformat(), "timeZone": "Europe/Zurich"},
        "end": {"dateTime": end.astimezone(TZ).isoformat(), "timeZone": "Europe/Zurich"},
    }

    created = service.events().insert(calendarId=calendar["id"], body=body).execute()
    return _event_to_dict(created, calendar)


def update_google_event(
    *,
    calendar_id: str,
    event_id: str,
    new_title: str | None = None,
    new_start: datetime | None = None,
    new_end: datetime | None = None,
) -> dict:
    if bool(new_start) != bool(new_end):
        raise ValueError("La nouvelle heure de début et de fin doivent être fournies ensemble.")
    if new_start and new_end and new_end <= new_start:
        raise ValueError("L'heure de fin doit être après l'heure de début.")
    if new_title is None and new_start is None:
        raise ValueError("Aucune modification demandée.")

    service = _service()
    calendar = _calendar_by_id(service, calendar_id)
    _assert_writable(calendar)

    body = {}
    if new_title is not None:
        body["summary"] = new_title
    if new_start is not None:
        body["start"] = {
            "dateTime": new_start.astimezone(TZ).isoformat(),
            "timeZone": "Europe/Zurich",
        }
        body["end"] = {
            "dateTime": new_end.astimezone(TZ).isoformat(),
            "timeZone": "Europe/Zurich",
        }

    updated = (
        service.events()
        .patch(calendarId=calendar_id, eventId=event_id, body=body)
        .execute()
    )
    return _event_to_dict(updated, calendar)


def delete_google_event(*, calendar_id: str, event_id: str) -> None:
    service = _service()
    calendar = _calendar_by_id(service, calendar_id)
    _assert_writable(calendar)
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
