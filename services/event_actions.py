from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from calendars.apple_calendar import (
    create_apple_event,
    delete_apple_event,
    update_apple_event,
)
from calendars.google_calendar import (
    create_google_event,
    delete_google_event,
    update_google_event,
)
from services.event_search import deserialize_event_ref

TZ = ZoneInfo("Europe/Zurich")


def _event_ref(event_or_data: dict) -> dict:
    if isinstance(event_or_data.get("start"), str):
        return deserialize_event_ref(event_or_data)
    return event_or_data


def delete_event(event_or_data: dict) -> dict:
    event = _event_ref(event_or_data)

    if event["provider"] == "google":
        delete_google_event(
            calendar_id=event["calendar_id"],
            event_id=event["id"],
        )
    elif event["provider"] == "apple":
        if event.get("recurring"):
            raise ValueError(
                "La suppression d'un événement Apple récurrent n'est pas encore "
                "prise en charge en V0.3 pour éviter de supprimer toute la série."
            )
        delete_apple_event(
            calendar_name=event["calendar_name"],
            uid=event["id"],
            resource_url=event.get("resource_url"),
        )
    else:
        raise ValueError("Source de calendrier inconnue.")

    return event


def rename_event(event_or_data: dict, new_title: str) -> dict:
    event = _event_ref(event_or_data)

    if event["provider"] == "google":
        updated = update_google_event(
            calendar_id=event["calendar_id"],
            event_id=event["id"],
            new_title=new_title,
        )
    elif event["provider"] == "apple":
        if event.get("recurring"):
            raise ValueError(
                "La modification d'un événement Apple récurrent n'est pas encore "
                "prise en charge en V0.3."
            )
        updated = update_apple_event(
            calendar_name=event["calendar_name"],
            uid=event["id"],
            resource_url=event.get("resource_url"),
            new_title=new_title,
        )
    else:
        raise ValueError("Source de calendrier inconnue.")

    return updated


def move_event(
    event_or_data: dict,
    *,
    target_date: str | date | None,
    target_hour: int,
    target_minute: int,
) -> dict:
    event = _event_ref(event_or_data)

    if event.get("all_day"):
        raise ValueError(
            "Le déplacement horaire des événements « toute la journée » n'est "
            "pas encore pris en charge en V0.3."
        )

    old_start = event["start"].astimezone(TZ)
    old_end = event.get("end")
    if old_end:
        old_end = old_end.astimezone(TZ)

    duration = (old_end - old_start) if old_end else timedelta(hours=1)
    if duration <= timedelta(0):
        duration = timedelta(hours=1)

    if isinstance(target_date, str):
        target_day = date.fromisoformat(target_date)
    elif isinstance(target_date, date):
        target_day = target_date
    else:
        target_day = old_start.date()

    new_start = datetime(
        target_day.year,
        target_day.month,
        target_day.day,
        target_hour,
        target_minute,
        tzinfo=TZ,
    )
    new_end = new_start + duration

    if event["provider"] == "google":
        return update_google_event(
            calendar_id=event["calendar_id"],
            event_id=event["id"],
            new_start=new_start,
            new_end=new_end,
        )

    if event["provider"] == "apple":
        if event.get("recurring"):
            raise ValueError(
                "Le déplacement d'un événement Apple récurrent n'est pas encore "
                "pris en charge en V0.3."
            )
        return update_apple_event(
            calendar_name=event["calendar_name"],
            uid=event["id"],
            resource_url=event.get("resource_url"),
            new_start=new_start,
            new_end=new_end,
        )

    raise ValueError("Source de calendrier inconnue.")



def transfer_event(
    event_or_data: dict,
    *,
    target_provider: str,
    target_calendar_name: str,
    target_date: str | date | None = None,
    target_hour: int | None = None,
    target_minute: int | None = None,
) -> dict:
    """Transfère un événement simple vers un autre calendrier.

    Le transfert crée d'abord l'événement dans la destination puis supprime
    l'original. En V0.3.1, le titre, la date, l'heure et la durée sont conservés.
    Les événements récurrents et "toute la journée" sont volontairement bloqués.
    """
    event = _event_ref(event_or_data)

    if target_provider not in {"google", "apple"}:
        raise ValueError("Le calendrier de destination doit être Google ou Apple.")

    if event.get("recurring"):
        raise ValueError(
            "Le transfert d'un événement récurrent n'est pas encore pris en charge."
        )

    if event.get("all_day"):
        raise ValueError(
            "Le transfert des événements « toute la journée » n'est pas encore pris en charge."
        )

    old_start = event["start"].astimezone(TZ)
    old_end = event.get("end")
    old_end = old_end.astimezone(TZ) if old_end else old_start + timedelta(hours=1)
    duration = old_end - old_start
    if duration <= timedelta(0):
        duration = timedelta(hours=1)

    if isinstance(target_date, str):
        target_day = date.fromisoformat(target_date)
    elif isinstance(target_date, date):
        target_day = target_date
    else:
        target_day = old_start.date()

    if target_hour is None:
        hour = old_start.hour
        minute = old_start.minute
    else:
        hour = int(target_hour)
        minute = int(target_minute or 0)

    new_start = datetime(
        target_day.year,
        target_day.month,
        target_day.day,
        hour,
        minute,
        tzinfo=TZ,
    )
    new_end = new_start + duration

    same_destination = (
        event.get("provider") == target_provider
        and event.get("calendar_name", "").casefold().strip()
        == target_calendar_name.casefold().strip()
    )

    # Si on vise exactement le même calendrier, un simple changement d'heure
    # reste une modification classique. Sans changement d'heure, rien à faire.
    if same_destination:
        if target_hour is None and target_date is None:
            raise ValueError("L'événement est déjà dans ce calendrier.")
        return move_event(
            event,
            target_date=target_date,
            target_hour=hour,
            target_minute=minute,
        )

    # Création destination AVANT suppression source : on évite de perdre
    # l'événement si la destination refuse l'écriture.
    if target_provider == "google":
        created = create_google_event(
            title=event["title"],
            start=new_start,
            end=new_end,
            calendar_name=target_calendar_name,
        )
    else:
        created = create_apple_event(
            title=event["title"],
            start=new_start,
            end=new_end,
            calendar_name=target_calendar_name,
        )

    try:
        delete_event(event)
    except Exception as source_error:
        # Tentative de rollback pour ne pas laisser un doublon si la suppression
        # de l'original échoue après création de la copie.
        rollback_error = None
        try:
            delete_event(created)
        except Exception as exc:
            rollback_error = exc

        if rollback_error:
            raise RuntimeError(
                "La destination a été créée mais l'original n'a pas pu être supprimé, "
                "et le rollback a aussi échoué. Vérifie les deux calendriers. "
                f"Suppression source: {source_error}; rollback: {rollback_error}"
            ) from source_error

        raise RuntimeError(
            "Le transfert a été annulé car l'événement source n'a pas pu être supprimé."
        ) from source_error

    return created
