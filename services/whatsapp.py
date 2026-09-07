import os
import requests

GRAPH_VERSION = os.getenv("WHATSAPP_GRAPH_VERSION", "v26.0")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")


def extract_text_messages(payload: dict) -> list[dict]:
    messages_found = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue

                text = message.get("text", {}).get("body", "").strip()
                sender = message.get("from")

                if sender and text:
                    messages_found.append({
                        "from": sender,
                        "text": text,
                    })

    return messages_found


def send_text_message(to: str, text: str) -> dict:
    if not ACCESS_TOKEN:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN manquant")
    if not PHONE_NUMBER_ID:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID manquant")

    url = (
        f"https://graph.facebook.com/"
        f"{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages"
    )

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "body": text,
                "preview_url": False,
            },
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json()
