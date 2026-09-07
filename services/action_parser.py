import re
from datetime import datetime

from services.event_parser import (
    DATE_PATTERN,
    TIME_PATTERN,
    parse_date_expression,
    parse_time,
)


def _normalize_spaces(text: str) -> str:
    return " ".join(text.strip().split())


def _extract_destination(body: str) -> tuple[str, str | None, str | None]:
    destination = re.search(
        r"\s+(?:dans|sur|de|du)\s+(google|apple|icloud)\s+(.+?)\s*$",
        body,
        flags=re.I,
    )
    if not destination:
        return body.strip(), None, None

    provider_raw = destination.group(1).lower()
    provider = "apple" if provider_raw in {"apple", "icloud"} else "google"
    calendar_name = destination.group(2).strip()
    return body[: destination.start()].strip(), provider, calendar_name


def _split_optional_source_date(body: str, now: datetime) -> tuple[str, object | None]:
    match = re.match(
        rf"^(?P<title>.+?)\s+(?:(?:de|du)\s+)?(?P<date>{DATE_PATTERN})$",
        body,
        flags=re.I,
    )
    if not match:
        return body.strip(), None

    title = match.group("title").strip()
    if not title:
        return body.strip(), None

    return title, parse_date_expression(match.group("date"), now)


def parse_search_command(text: str, now: datetime) -> dict:
    raw = _normalize_spaces(text)
    verb = re.match(r"^(cherche|recherche|trouve)\s+", raw, flags=re.I)
    if not verb:
        raise ValueError("Commande de recherche non reconnue.")

    body, provider, calendar_name = _extract_destination(raw[verb.end():].strip())
    title, event_date = _split_optional_source_date(body, now)

    if not title:
        raise ValueError("Précise le nom de l'événement à rechercher.")

    return {
        "action": "search",
        "title": title,
        "event_date": event_date,
        "provider": provider,
        "calendar_name": calendar_name,
    }


def parse_delete_command(text: str, now: datetime) -> dict:
    raw = _normalize_spaces(text)
    verb = re.match(r"^(supprime|supprimer|efface|effacer)\s+", raw, flags=re.I)
    if not verb:
        raise ValueError("Commande de suppression non reconnue.")

    body, provider, calendar_name = _extract_destination(raw[verb.end():].strip())
    title, event_date = _split_optional_source_date(body, now)

    if not title:
        raise ValueError("Précise l'événement à supprimer.")

    return {
        "action": "delete",
        "title": title,
        "event_date": event_date,
        "provider": provider,
        "calendar_name": calendar_name,
    }


def parse_rename_command(text: str, now: datetime) -> dict:
    raw = _normalize_spaces(text)
    verb = re.match(r"^(renomme|renommer)\s+", raw, flags=re.I)
    if not verb:
        raise ValueError("Commande de renommage non reconnue.")

    body, provider, calendar_name = _extract_destination(raw[verb.end():].strip())

    match = re.match(r"^(?P<old>.+?)\s+en\s+(?P<new>.+)$", body, flags=re.I)
    if not match:
        raise ValueError("Exemple : « Renomme Test Bot en Dentiste ». ")

    old_part = match.group("old").strip()
    new_title = match.group("new").strip()
    old_title, event_date = _split_optional_source_date(old_part, now)

    if not old_title or not new_title:
        raise ValueError("Le titre actuel et le nouveau titre sont obligatoires.")

    return {
        "action": "rename",
        "title": old_title,
        "new_title": new_title,
        "event_date": event_date,
        "provider": provider,
        "calendar_name": calendar_name,
    }


def _extract_target_destination(body: str) -> tuple[str, str | None, str | None]:
    """Extrait une destination de transfert en fin de commande.

    Exemples :
    - "Test Bot vers Apple César"
    - "Test Bot dans Google Travail"
    """
    destination = re.search(
        r"\s+(?:vers|sur|dans)\s+(google|apple|icloud)\s+(.+?)\s*$",
        body,
        flags=re.I,
    )
    if not destination:
        return body.strip(), None, None

    provider_raw = destination.group(1).lower()
    provider = "apple" if provider_raw in {"apple", "icloud"} else "google"
    calendar_name = destination.group(2).strip()
    return body[: destination.start()].strip(), provider, calendar_name


def parse_move_command(text: str, now: datetime) -> dict:
    raw = _normalize_spaces(text)
    verb = re.match(
        r"^(déplace|deplace|déplacer|deplacer|transfère|transfere|transférer|transferer|modifie|modifier)\s+",
        raw,
        flags=re.I,
    )
    if not verb:
        raise ValueError("Commande de déplacement non reconnue.")

    original_body = raw[verb.end():].strip()

    # D'abord, on regarde si la commande demande un changement de calendrier.
    # Ici la destination n'est PAS un filtre de recherche de l'événement source.
    body, target_provider, target_calendar_name = _extract_target_destination(original_body)

    if target_provider:
        # Optionnel : changement de calendrier + nouvelle date/heure.
        # Ex. "Déplace Dentiste demain à 16h vers Apple César"
        with_date = re.match(
            rf"^(?P<title>.+?)\s+(?P<date>{DATE_PATTERN})\s+(?:a|à)\s+(?P<time>{TIME_PATTERN})$",
            body,
            flags=re.I,
        )

        if with_date:
            title = with_date.group("title").strip()
            target_date = parse_date_expression(with_date.group("date"), now)
            hour, minute = parse_time(with_date.group("time"))
        else:
            no_date = re.match(
                rf"^(?P<title>.+?)\s+(?:a|à)\s+(?P<time>{TIME_PATTERN})$",
                body,
                flags=re.I,
            )
            if no_date:
                title = no_date.group("title").strip()
                target_date = None
                hour, minute = parse_time(no_date.group("time"))
            else:
                # Transfert pur : on conserve date, heure et durée.
                title = body.strip()
                target_date = None
                hour = None
                minute = None

        if not title:
            raise ValueError("Précise l'événement à déplacer.")
        if not target_calendar_name:
            raise ValueError("Précise le calendrier de destination.")

        return {
            "action": "transfer",
            "title": title,
            "event_date": None,
            "provider": None,
            "calendar_name": None,
            "target_provider": target_provider,
            "target_calendar_name": target_calendar_name,
            "target_date": target_date.isoformat() if target_date else None,
            "target_hour": hour,
            "target_minute": minute,
        }

    # Déplacement horaire classique. Ici "dans Google X" peut servir de filtre
    # pour préciser l'événement source, comme en V0.3.
    body, provider, calendar_name = _extract_destination(original_body)

    with_date = re.match(
        rf"^(?P<title>.+?)\s+(?P<date>{DATE_PATTERN})\s+(?:a|à)\s+(?P<time>{TIME_PATTERN})$",
        body,
        flags=re.I,
    )

    if with_date:
        title = with_date.group("title").strip()
        target_date = parse_date_expression(with_date.group("date"), now)
        hour, minute = parse_time(with_date.group("time"))
    else:
        no_date = re.match(
            rf"^(?P<title>.+?)\s+(?:a|à)\s+(?P<time>{TIME_PATTERN})$",
            body,
            flags=re.I,
        )
        if not no_date:
            raise ValueError(
                "Exemples : « Déplace Dentiste demain à 16h » ou "
                "« Déplace Dentiste vers Apple César »."
            )
        title = no_date.group("title").strip()
        target_date = None
        hour, minute = parse_time(no_date.group("time"))

    if not title:
        raise ValueError("Précise l'événement à déplacer.")

    return {
        "action": "move",
        "title": title,
        "event_date": None,
        "provider": provider,
        "calendar_name": calendar_name,
        "target_date": target_date.isoformat() if target_date else None,
        "target_hour": hour,
        "target_minute": minute,
    }
