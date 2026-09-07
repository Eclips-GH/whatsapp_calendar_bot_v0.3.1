import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from calendars.google_calendar import (
    create_google_event,
    google_is_configured,
    list_google_calendars,
    list_google_events,
    list_google_writable_calendars,
)
from calendars.apple_calendar import (
    apple_is_configured,
    create_apple_event,
    list_apple_calendars,
    list_apple_events,
)
from services.action_parser import (
    parse_delete_command,
    parse_move_command,
    parse_rename_command,
    parse_search_command,
)
from services.event_actions import delete_event, move_event, rename_event, transfer_event
from services.event_parser import DATE_PATTERN, parse_create_command, parse_date_expression
from services.event_search import find_events, serializable_event_ref
from services.pending_store import clear_pending, get_pending, save_pending

TZ = ZoneInfo("Europe/Zurich")


def _format_events(events: list[dict], label: str) -> str:
    if not events:
        return f"📅 {label}\nAucun événement."

    lines = [f"📅 {label}"]
    for event in sorted(events, key=lambda e: e["sort"]):
        time_text = "Toute la journée" if event.get("all_day") else event["start"].strftime("%H:%M")
        lines.append(f"{time_text} — {event['title']} [{event['source']}]")
    return "\n".join(lines)


def _events_for_date(target: date, label: str) -> str:
    start = datetime(target.year, target.month, target.day, tzinfo=TZ)
    end = start + timedelta(days=1)

    events = []
    errors = []

    if google_is_configured():
        try:
            events.extend(list_google_events(start, end))
        except Exception as exc:
            errors.append(f"Google: {exc}")

    if apple_is_configured():
        try:
            events.extend(list_apple_events(start, end))
        except Exception as exc:
            errors.append(f"Apple: {exc}")

    if not google_is_configured() and not apple_is_configured():
        return "⚠️ Aucun calendrier n'est encore configuré."

    result = _format_events(events, label)
    if errors:
        result += "\n\n⚠️ " + " | ".join(errors)
    return result


def _events_for_day(day_offset: int, label: str) -> str:
    now = datetime.now(TZ)
    target = (now + timedelta(days=day_offset)).date()
    return _events_for_date(target, label)


def _date_query(text: str) -> tuple[date, str] | None:
    raw = " ".join(text.strip().split())
    lowered = raw.casefold()

    # Permet aussi « agenda samedi » ou « j'ai quoi vendredi ».
    prefixes = (
        "agenda ",
        "j'ai quoi ",
        "jai quoi ",
        "qu'est-ce que j'ai ",
        "qu est ce que j ai ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            raw = raw[len(prefix):].strip()
            break

    if not re.fullmatch(DATE_PATTERN, raw, flags=re.I):
        return None

    target = parse_date_expression(raw, datetime.now(TZ))
    weekdays = (
        "Lundi", "Mardi", "Mercredi", "Jeudi",
        "Vendredi", "Samedi", "Dimanche"
    )
    label = f"{weekdays[target.weekday()]} {target.strftime('%d.%m.%Y')}"
    return target, label


def _calendar_list() -> str:
    lines = ["🗓️ Calendriers connectés"]

    if google_is_configured():
        try:
            names = list_google_calendars()
            lines.append("\nGoogle :")
            lines.extend(f"• {name}" for name in names)
        except Exception as exc:
            lines.append(f"\nGoogle : erreur ({exc})")
    else:
        lines.append("\nGoogle : non configuré")

    if apple_is_configured():
        try:
            names = list_apple_calendars()
            lines.append("\nApple/iCloud :")
            lines.extend(f"• {name}" for name in names)
        except Exception as exc:
            lines.append(f"\nApple/iCloud : erreur ({exc})")
    else:
        lines.append("\nApple/iCloud : non configuré")

    return "\n".join(lines)


def _writable_calendar_list() -> str:
    lines = ["✏️ Calendriers utilisables pour créer/modifier un événement"]

    if google_is_configured():
        try:
            names = list_google_writable_calendars()
            lines.append("\nGoogle :")
            lines.extend(f"• {name}" for name in names) if names else lines.append("• Aucun calendrier modifiable")
        except Exception as exc:
            lines.append(f"\nGoogle : erreur ({exc})")

    if apple_is_configured():
        try:
            names = list_apple_calendars()
            lines.append("\nApple/iCloud :")
            lines.extend(f"• {name}" for name in names) if names else lines.append("• Aucun calendrier")
        except Exception as exc:
            lines.append(f"\nApple/iCloud : erreur ({exc})")

    return "\n".join(lines)


def _format_created_event(event: dict) -> str:
    start = event["start"].astimezone(TZ)
    end = event["end"].astimezone(TZ)
    return (
        "✅ Événement créé\n"
        f"• {event['title']}\n"
        f"• {start.strftime('%d.%m.%Y')} de {start.strftime('%H:%M')} à {end.strftime('%H:%M')}\n"
        f"• [{event['source']}]"
    )


def _create_from_command(text: str) -> str:
    command = parse_create_command(text)

    if command["provider"] == "google":
        if not google_is_configured():
            return "⚠️ Google Calendar n'est pas configuré."
        event = create_google_event(
            title=command["title"],
            start=command["start"],
            end=command["end"],
            calendar_name=command["calendar_name"],
        )
    else:
        if not apple_is_configured():
            return "⚠️ Apple/iCloud n'est pas configuré."
        event = create_apple_event(
            title=command["title"],
            start=command["start"],
            end=command["end"],
            calendar_name=command["calendar_name"],
        )

    return _format_created_event(event)


def _format_event_line(event: dict, number: int | None = None) -> str:
    start = event["start"].astimezone(TZ)
    if event.get("all_day"):
        when = start.strftime("%d.%m.%Y") + " toute la journée"
    else:
        when = start.strftime("%d.%m.%Y %H:%M")
    prefix = f"{number}. " if number is not None else "• "
    return f"{prefix}{event['title']} — {when} [{event['source']}]"


def _format_search_results(events: list[dict]) -> str:
    if not events:
        return "🔎 Aucun événement trouvé."

    lines = [f"🔎 {len(events)} événement(s) trouvé(s) :"]
    for index, event in enumerate(events[:10], start=1):
        lines.append(_format_event_line(event, index))
    if len(events) > 10:
        lines.append(f"… et {len(events) - 10} autre(s).")
    return "\n".join(lines)


def _pending_payload(command: dict) -> dict:
    payload = {"action": command["action"]}
    for key in (
        "new_title",
        "target_date",
        "target_hour",
        "target_minute",
        "target_provider",
        "target_calendar_name",
    ):
        if key in command:
            payload[key] = command[key]
    return payload


def _ambiguity_message(command: dict, events: list[dict], user_id: str) -> str:
    options = [serializable_event_ref(event) for event in events[:20]]
    save_pending(user_id, _pending_payload(command), options)

    lines = [f"J'ai trouvé {len(events)} événements correspondants :"]
    for index, event in enumerate(events[:20], start=1):
        lines.append(_format_event_line(event, index))
    if len(events) > 20:
        lines.append("Affichage limité aux 20 premiers résultats.")
    lines.append("\nRéponds simplement avec le numéro, ou « annule ».")
    return "\n".join(lines)


def _execute_event_action(action: dict, event: dict) -> str:
    action_type = action["action"]

    if action_type == "delete":
        deleted = delete_event(event)
        return f"✅ Événement supprimé\n• {deleted['title']}\n• [{deleted['source']}]"

    if action_type == "rename":
        updated = rename_event(event, action["new_title"])
        return (
            "✅ Événement renommé\n"
            f"• {updated['title']}\n"
            f"• [{updated['source']}]"
        )

    if action_type == "move":
        updated = move_event(
            event,
            target_date=action.get("target_date"),
            target_hour=int(action["target_hour"]),
            target_minute=int(action["target_minute"]),
        )
        start = updated["start"].astimezone(TZ)
        end = updated["end"].astimezone(TZ)
        return (
            "✅ Événement déplacé\n"
            f"• {updated['title']}\n"
            f"• {start.strftime('%d.%m.%Y')} de {start.strftime('%H:%M')} à {end.strftime('%H:%M')}\n"
            f"• [{updated['source']}]"
        )

    if action_type == "transfer":
        updated = transfer_event(
            event,
            target_provider=action["target_provider"],
            target_calendar_name=action["target_calendar_name"],
            target_date=action.get("target_date"),
            target_hour=action.get("target_hour"),
            target_minute=action.get("target_minute"),
        )
        start = updated["start"].astimezone(TZ)
        end = updated["end"].astimezone(TZ)
        return (
            "✅ Événement transféré\n"
            f"• {updated['title']}\n"
            f"• {start.strftime('%d.%m.%Y')} de {start.strftime('%H:%M')} à {end.strftime('%H:%M')}\n"
            f"• [{updated['source']}]"
        )

    raise ValueError("Action inconnue.")


def _resolve_action(command: dict, user_id: str) -> str:
    events = find_events(
        command["title"],
        event_date=command.get("event_date"),
        provider=command.get("provider"),
        calendar_name=command.get("calendar_name"),
    )

    if not events:
        return "🔎 Aucun événement correspondant trouvé."

    if len(events) > 1:
        return _ambiguity_message(command, events, user_id)

    clear_pending(user_id)
    return _execute_event_action(_pending_payload(command), events[0])


def _handle_pending_choice(text: str, user_id: str) -> str | None:
    pending = get_pending(user_id)
    if not pending:
        return None

    normalized = text.strip().lower()
    if normalized in {"annule", "annuler", "cancel"}:
        clear_pending(user_id)
        return "✅ Action annulée."

    if not normalized.isdigit():
        return None

    choice = int(normalized)
    options = pending["options"]
    if not (1 <= choice <= len(options)):
        return f"Choisis un numéro entre 1 et {len(options)}, ou écris « annule »."

    clear_pending(user_id)
    return _execute_event_action(pending["action"], options[choice - 1])


def _search_from_command(text: str) -> str:
    command = parse_search_command(text, datetime.now(TZ))
    events = find_events(
        command["title"],
        event_date=command.get("event_date"),
        provider=command.get("provider"),
        calendar_name=command.get("calendar_name"),
    )
    return _format_search_results(events)


def handle_command(text: str, user_id: str = "local") -> str:
    pending_reply = _handle_pending_choice(text, user_id)
    if pending_reply is not None:
        return pending_reply

    normalized = text.strip().lower()

    if normalized in {"ping", "test"}:
        return "✅ Bot en ligne."

    if normalized in {"aide", "help", "commandes", "menu"}:
        return (
            "Commandes V0.4 :\n"
            "• calendriers\n"
            "• calendriers modifiables\n"
            "• aujourd'hui / demain / samedi / 12.09.2026\n"
            "• Cherche Dentiste\n"
            "• Ajoute Dentiste demain à 14h dans Google Travail\n"
            "• Supprime Dentiste\n"
            "• Supprime Dentiste demain\n"
            "• Supprime Dentiste de Apple Domicile\n"
            "• Renomme Dentiste en Contrôle dentiste\n"
            "• Déplace Dentiste demain à 16h\n"
            "• Déplace Dentiste vers Apple César\n"
            "• Déplace Dentiste demain à 16h vers Google Travail\n\n"
            "Si plusieurs événements correspondent, réponds avec le numéro."
        )

    if normalized in {"calendriers", "mes calendriers", "liste calendriers"}:
        return _calendar_list()

    if normalized in {"calendriers modifiables", "calendriers écriture", "calendriers ecriture"}:
        return _writable_calendar_list()

    if normalized in {"aujourd'hui", "aujourdhui", "j'ai quoi aujourd'hui", "jai quoi aujourd'hui", "agenda aujourd'hui"}:
        return _events_for_day(0, "Aujourd'hui")

    if normalized in {"demain", "j'ai quoi demain", "jai quoi demain", "agenda demain"}:
        return _events_for_day(1, "Demain")

    parsed_date_query = _date_query(text)
    if parsed_date_query is not None:
        target, label = parsed_date_query
        return _events_for_date(target, label)

    try:
        if normalized.startswith(("ajoute ", "ajouter ", "crée ", "cree ", "créer ", "creer ")):
            return _create_from_command(text)

        if normalized.startswith(("cherche ", "recherche ", "trouve ")):
            return _search_from_command(text)

        if normalized.startswith(("supprime ", "supprimer ", "efface ", "effacer ")):
            command = parse_delete_command(text, datetime.now(TZ))
            return _resolve_action(command, user_id)

        if normalized.startswith(("renomme ", "renommer ")):
            command = parse_rename_command(text, datetime.now(TZ))
            return _resolve_action(command, user_id)

        if normalized.startswith((
            "déplace ", "deplace ", "déplacer ", "deplacer ",
            "transfère ", "transfere ", "transférer ", "transferer ",
            "modifie ", "modifier "
        )):
            command = parse_move_command(text, datetime.now(TZ))
            return _resolve_action(command, user_id)

    except (ValueError, PermissionError) as exc:
        return f"❌ {exc}"
    except Exception as exc:
        return f"❌ Action impossible : {exc}"

    return "Je ne comprends pas encore cette commande.\nÉcris « aide » pour voir les commandes disponibles."
