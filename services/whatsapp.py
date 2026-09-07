import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_VERSION = os.getenv("WHATSAPP_GRAPH_VERSION", "v26.0").strip()
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()


def normalize_phone_number(value: str) -> str:
    """Normalise un numéro WhatsApp en chiffres uniquement, par ex. +41 79 -> 4179."""
    return re.sub(r"\D", "", value or "")


def allowed_numbers() -> set[str]:
    raw = os.getenv("WHATSAPP_ALLOWED_NUMBERS", "")
    return {
        normalize_phone_number(item)
        for item in raw.split(",")
        if normalize_phone_number(item)
    }


def sender_is_allowed(sender: str) -> bool:
    allowed = allowed_numbers()
    if not allowed:
        # Pour un bot calendrier personnel, on refuse par défaut tant qu'une
        # liste blanche n'a pas été configurée explicitement.
        return False
    return normalize_phone_number(sender) in allowed


def extract_text_messages(payload: dict) -> list[dict]:
    messages_found = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue

                text = message.get("text", {}).get("body", "").strip()
                sender = normalize_phone_number(message.get("from", ""))
                message_id = message.get("id")

                if sender and text:
                    messages_found.append({
                        "id": message_id,
                        "from": sender,
                        "text": text,
                        "timestamp": message.get("timestamp"),
                    })

    return messages_found


def whatsapp_is_configured() -> bool:
    return bool(ACCESS_TOKEN and PHONE_NUMBER_ID)


def send_text_message(to: str, text: str) -> dict:
    if not ACCESS_TOKEN:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN manquant")
    if not PHONE_NUMBER_ID:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID manquant")

    recipient = normalize_phone_number(to)
    if not recipient:
        raise ValueError("Numéro WhatsApp destinataire invalide")

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {
                "body": text[:4096],
                "preview_url": False,
            },
        },
        timeout=20,
    )

    if not response.ok:
        try:
            details = response.json()
        except Exception:
            details = response.text[:1000]
        raise RuntimeError(
            f"Meta WhatsApp API HTTP {response.status_code}: {details}"
        )

    return response.json()
