import os
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import caldav
from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo("Europe/Zurich")
APPLE_CALDAV_URL = os.getenv("APPLE_CALDAV_URL", "https://caldav.icloud.com/")
APPLE_EMAIL = os.getenv("APPLE_EMAIL", "")
APPLE_APP_PASSWORD = os.getenv("APPLE_APP_PASSWORD", "")


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.casefold().split())


def apple_is_configured() -> bool:
    return bool(APPLE_EMAIL and APPLE_APP_PASSWORD)


def _client():
    if not apple_is_configured():
        raise RuntimeError("Identifiants Apple/iCloud manquants")

    return caldav.DAVClient(
        url=APPLE_CALDAV_URL,
        username=APPLE_EMAIL,
        password=APPLE_APP_PASSWORD,
    )


def list_apple_calendars() -> list[str]:
    with _client() as client:
        calendars = client.principal().calendars()
        return [calendar.get_display_name() or "Sans nom" for calendar in calendars]


def _find_apple_calendar(calendars, calendar_name: str):
    wanted = _normalize_name(calendar_name)
    matches = [
        calendar
        for calendar in calendars
        if _normalize_name(calendar.get_display_name() or "Sans nom") == wanted
    ]

    if not matches:
        available = ", ".join(
            calendar.get_display_name() or "Sans nom" for calendar in calendars
        )
        raise ValueError(
            f"Calendrier Apple '{calendar_name}' introuvable. Disponibles : {available}"
        )

    if len(matches) > 1:
        raise ValueError(
            f"Plusieurs calendriers Apple portent le nom '{calendar_name}'. "
            "Renomme-en un pour éviter l'ambiguïté."
        )

    return matches[0]


def _normalize_dt(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ)
        else:
            value = value.astimezone(TZ)
        return value, False

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=TZ), True

    raise ValueError(f"Date iCloud non reconnue : {value!r}")


def _resource_by_uid(calendar, uid: str):
    if hasattr(calendar, "get_event_by_uid"):
        return calendar.get_event_by_uid(uid)
    return calendar.event_by_uid(uid)


def _component_to_dict(component, calendar_name: str) -> dict:
    start_dt, all_day = _normalize_dt(component.decoded("DTSTART"))

    if component.get("DTEND") is not None:
        end_dt, _ = _normalize_dt(component.decoded("DTEND"))
    else:
        end_dt = start_dt + (timedelta(days=1) if all_day else timedelta(hours=1))

    summary_value = component.get("SUMMARY")
    summary = str(summary_value) if summary_value else "(Sans titre)"
    uid = str(component.get("UID", ""))

    return {
        "title": summary,
        "start": start_dt,
        "end": end_dt,
        "sort": start_dt,
        "all_day": all_day,
        "source": f"Apple • {calendar_name}",
        "provider": "apple",
        "calendar_name": calendar_name,
        "id": uid,
        "recurring": bool(component.get("RRULE") or component.get("RECURRENCE-ID")),
    }


def list_apple_events(start: datetime, end: datetime) -> list[dict]:
    output = []

    with _client() as client:
        calendars = client.principal().calendars()

        for calendar in calendars:
            calendar_name = calendar.get_display_name() or "Sans nom"

            try:
                found = calendar.search(event=True, start=start, end=end, expand=True)
            except Exception as exc:
                print(f"Erreur calendrier Apple '{calendar_name}' : {exc}")
                continue

            for event in found:
                try:
                    output.append(
                        _component_to_dict(event.get_icalendar_component(), calendar_name)
                    )
                except Exception as exc:
                    print(f"Erreur événement Apple dans '{calendar_name}' : {exc}")

    return output


def create_apple_event(title: str, start: datetime, end: datetime, calendar_name: str) -> dict:
    if end <= start:
        raise ValueError("L'heure de fin doit être après l'heure de début.")

    with _client() as client:
        calendars = client.principal().calendars()
        calendar = _find_apple_calendar(calendars, calendar_name)
        resolved_name = calendar.get_display_name() or calendar_name

        created = calendar.add_event(
            summary=title,
            dtstart=start.astimezone(TZ),
            dtend=end.astimezone(TZ),
        )

        try:
            return _component_to_dict(created.get_icalendar_component(), resolved_name)
        except Exception:
            return {
                "id": "",
                "title": title,
                "start": start.astimezone(TZ),
                "end": end.astimezone(TZ),
                "sort": start.astimezone(TZ),
                "all_day": False,
                "provider": "apple",
                "calendar_name": resolved_name,
                "source": f"Apple • {resolved_name}",
                "recurring": False,
            }


def update_apple_event(
    *,
    calendar_name: str,
    uid: str,
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

    with _client() as client:
        calendars = client.principal().calendars()
        calendar = _find_apple_calendar(calendars, calendar_name)
        resolved_name = calendar.get_display_name() or calendar_name
        resource = _resource_by_uid(calendar, uid)

        with resource.edit_icalendar_component() as component:
            if new_title is not None:
                component["SUMMARY"] = new_title

            if new_start is not None:
                if component.get("DTSTART") is not None:
                    del component["DTSTART"]
                component.add("DTSTART", new_start.astimezone(TZ))

                if component.get("DTEND") is not None:
                    del component["DTEND"]
                component.add("DTEND", new_end.astimezone(TZ))

        resource.save()
        return _component_to_dict(resource.get_icalendar_component(), resolved_name)


def delete_apple_event(*, calendar_name: str, uid: str) -> None:
    with _client() as client:
        calendars = client.principal().calendars()
        calendar = _find_apple_calendar(calendars, calendar_name)
        resource = _resource_by_uid(calendar, uid)
        resource.delete()
