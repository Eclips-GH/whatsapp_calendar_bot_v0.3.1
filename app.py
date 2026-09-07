import os
import hmac
import hashlib
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

load_dotenv()

from services.whatsapp import (
    allowed_numbers,
    extract_text_messages,
    sender_is_allowed,
    send_text_message,
    whatsapp_is_configured,
)
from services.whatsapp_state import claim_message
from services.command_router import handle_command

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()


def signature_is_valid(raw_body: bytes, signature_header: str | None) -> bool:
    """Valide X-Hub-Signature-256 si META_APP_SECRET est configuré."""
    if not META_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        META_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, received)


@app.get("/")
def home():
    return {
        "service": "WhatsApp Calendar Bot",
        "version": "0.4",
        "status": "ok",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "whatsapp": {
            "configured": whatsapp_is_configured(),
            "verify_token_configured": bool(VERIFY_TOKEN),
            "app_secret_configured": bool(META_APP_SECRET),
            "allowed_numbers": len(allowed_numbers()),
        },
    }


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN:
        return challenge or "", 200

    return "Webhook verification failed", 403


@app.post("/webhook")
def receive_webhook():
    raw_body = request.get_data()

    if not signature_is_valid(
        raw_body,
        request.headers.get("X-Hub-Signature-256"),
    ):
        abort(403)

    payload = request.get_json(silent=True) or {}

    for message in extract_text_messages(payload):
        sender = message["from"]
        text = message["text"]
        message_id = message.get("id")

        if not sender_is_allowed(sender):
            print(f"WhatsApp sender ignored (not allowed): {sender}")
            continue

        # Meta peut renvoyer un webhook. On bloque les doublons AVANT
        # d'exécuter une action calendrier, afin d'éviter deux créations.
        if not claim_message(message_id):
            print(f"Duplicate WhatsApp message ignored: {message_id}")
            continue

        try:
            reply = handle_command(text, user_id=sender)
        except Exception as exc:
            print(f"Command error: {exc}")
            reply = "❌ Une erreur est survenue pendant le traitement de ta commande."

        try:
            send_text_message(sender, reply)
        except Exception as exc:
            print(f"WhatsApp send error: {exc}")

    # Meta attend un HTTP 200 rapide pour accuser réception du webhook.
    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
