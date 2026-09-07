"""
À lancer UNE FOIS sur ton PC pour créer token.json.

Pré-requis :
1. credentials.json dans le même dossier
2. pip install -r requirements.txt
3. python google_auth.py
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE = Path("token.json")


def main():
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            "credentials.json introuvable. "
            "Télécharge-le depuis Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES,
    )

    creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(
        creds.to_json(),
        encoding="utf-8",
    )

    print("✅ token.json créé.")


if __name__ == "__main__":
    main()
