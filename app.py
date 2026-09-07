import os
import hmac
import hashlib
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

load_dotenv()

from services.whatsapp import extract_text_messages, send_text_message
from services.command_router import handle_command

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")


def signature_is_valid(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Meta peut signer les webhooks avec X-Hub-Signature-256.
    Si META_APP_SECRET n'est pas configuré, on n'effectue pas cette vérification.
    """
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
        "status": "ok"
    }


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
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

        try:
            reply = handle_command(text, user_id=sender)
        except Exception as exc:
            print(f"Command error: {exc}")
            reply = "❌ Une erreur est survenue pendant le traitement de ta commande."

        try:
            send_text_message(sender, reply)
        except Exception as exc:
            print(f"WhatsApp send error: {exc}")

    # WhatsApp attend une réponse HTTP rapide.
    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
