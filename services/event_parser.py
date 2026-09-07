import re
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Zurich")

MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}

WEEKDAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}

DATE_PATTERN = (
    r"aujourd['’]?hui|demain|après-demain|apres-demain|"
    r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|"
    r"(?:le\s+)?\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?|"
    r"(?:le\s+)?\d{1,2}\s+[A-Za-zÀ-ÿ]+(?:\s+\d{4})?"
)

TIME_PATTERN = r"\d{1,2}(?:h|:)\d{0,2}"


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold()


def parse_time(value: str) -> tuple[int, int]:
    value = value.strip().lower().replace(" ", "")

    match = re.fullmatch(r"(\d{1,2})(?:h|:)(\d{2})?", value)
    if not match:
        raise ValueError(f"Heure non reconnue : {value}")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Heure invalide : {value}")

    return hour, minute


def _parse_duration(value: str | None) -> timedelta:
    if not value:
        return timedelta(hours=1)

    folded = _fold(value).replace(" ", "")

    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)min)?", folded)
    if not match or not any(match.groups()):
        raise ValueError(
            "Durée non reconnue. Exemples : 30min, 1h, 1h30min."
        )

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    duration = timedelta(hours=hours, minutes=minutes)

    if duration <= timedelta(0):
        raise ValueError("La durée doit être supérieure à 0 minute.")

    return duration


def _next_weekday(today: date, weekday: int) -> date:
    days = (weekday - today.weekday()) % 7
    return today + timedelta(days=days)


def parse_date_expression(value: str, now: datetime) -> date:
    folded = " ".join(_fold(value).strip().split())
    today = now.date()

    if folded in {"aujourd'hui", "aujourdhui"}:
        return today

    if folded == "demain":
        return today + timedelta(days=1)

    if folded == "apres-demain":
        return today + timedelta(days=2)

    if folded in WEEKDAYS:
        return _next_weekday(today, WEEKDAYS[folded])

    numeric = re.fullmatch(
        r"(?:le )?(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?",
        folded,
    )
    if numeric:
        day = int(numeric.group(1))
        month = int(numeric.group(2))
        year_text = numeric.group(3)
        year = int(year_text) if year_text else now.year
        if year < 100:
            year += 2000
        result = date(year, month, day)
        if not year_text and result < today:
            result = date(year + 1, month, day)
        return result

    named = re.fullmatch(
        r"(?:le )?(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?",
        folded,
    )
    if named:
        day = int(named.group(1))
        month_name = named.group(2)
        if month_name not in MONTHS:
            raise ValueError(f"Mois non reconnu : {month_name}")
        month = MONTHS[month_name]
        year_text = named.group(3)
        year = int(year_text) if year_text else now.year
        result = date(year, month, day)
        if not year_text and result < today:
            result = date(year + 1, month, day)
        return result

    raise ValueError(
        "Date non reconnue. Exemples : demain, samedi, 12/09/2026, 12 septembre."
    )


def parse_create_command(text: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)
    else:
        now = now.astimezone(TZ)

    raw = " ".join(text.strip().split())

    verb = re.match(r"^(ajoute|ajouter|cree|crée|creer|créer)\s+", raw, flags=re.I)
    if not verb:
        raise ValueError("La commande doit commencer par « Ajoute » ou « Crée ». ")

    body = raw[verb.end():].strip()

    destination = re.search(
        r"\s+dans\s+(google|apple|icloud)\s+(.+?)\s*$",
        body,
        flags=re.I,
    )
    if not destination:
        raise ValueError(
            "Précise la destination, par exemple « dans Google Travail » "
            "ou « dans Apple César »."
        )

    provider_raw = destination.group(1).lower()
    provider = "apple" if provider_raw in {"apple", "icloud"} else "google"
    calendar_name = destination.group(2).strip()
    before_destination = body[: destination.start()].strip()

    range_match = re.match(
        rf"^(?P<title>.+?)\s+(?P<date>{DATE_PATTERN})\s+"
        rf"de\s+(?P<start>{TIME_PATTERN})\s+(?:a|à)\s+(?P<end>{TIME_PATTERN})$",
        before_destination,
        flags=re.I,
    )

    duration_match = None
    if not range_match:
        duration_match = re.match(
            rf"^(?P<title>.+?)\s+(?P<date>{DATE_PATTERN})\s+"
            rf"(?:a|à)\s+(?P<start>{TIME_PATTERN})"
            r"(?:\s+pendant\s+(?P<duration>(?:(?:\d+)h)?(?:(?:\d+)min)?))?$",
            before_destination,
            flags=re.I,
        )

    match = range_match or duration_match
    if not match:
        raise ValueError(
            "Format non reconnu. Exemple : « Ajoute Dentiste demain à 14h "
            "dans Google Travail »."
        )

    title = match.group("title").strip()
    if not title:
        raise ValueError("Le titre de l'événement est vide.")

    event_date = parse_date_expression(match.group("date"), now)
    start_hour, start_minute = parse_time(match.group("start"))
    start = datetime(
        event_date.year,
        event_date.month,
        event_date.day,
        start_hour,
        start_minute,
        tzinfo=TZ,
    )

    if range_match:
        end_hour, end_minute = parse_time(match.group("end"))
        end = datetime(
            event_date.year,
            event_date.month,
            event_date.day,
            end_hour,
            end_minute,
            tzinfo=TZ,
        )
        if end <= start:
            raise ValueError("L'heure de fin doit être après l'heure de début.")
    else:
        duration = _parse_duration(match.group("duration"))
        end = start + duration

    return {
        "action": "create",
        "title": title,
        "provider": provider,
        "calendar_name": calendar_name,
        "start": start,
        "end": end,
    }
