# WhatsApp Calendar Bot — V0.4

V0.4 branche le moteur calendrier existant sur WhatsApp Cloud API.

## Fonctions calendrier

- Google Calendar + Apple/iCloud ;
- lecture de tous les calendriers avec provenance ;
- création ;
- recherche ;
- renommage ;
- déplacement date/heure ;
- transfert Google ↔ Apple ;
- suppression ;
- ambiguïtés par choix numéroté.

## Nouveautés V0.4

- webhook WhatsApp `GET/POST /webhook` ;
- réponses texte via Meta Graph API ;
- liste blanche `WHATSAPP_ALLOWED_NUMBERS` ;
- déduplication des messages Meta avec SQLite ;
- validation `X-Hub-Signature-256` si `META_APP_SECRET` est configuré ;
- diagnostic `GET /health`.

## Mise à jour depuis V0.3.2

Extraire le ZIP UPDATE directement dans le dossier existant. Ne pas supprimer :

```text
.env
credentials.json
token.json
venv/
bot_state.db
```

Aucune nouvelle dépendance Python.

## Configuration `.env`

Ajouter :

```env
WHATSAPP_VERIFY_TOKEN=<valeur aléatoire>
META_APP_SECRET=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ALLOWED_NUMBERS=41791234567
WHATSAPP_GRAPH_VERSION=v26.0
WHATSAPP_STATE_DB=whatsapp_state.db
```

Le numéro autorisé est en format international, chiffres uniquement. Exemple Suisse : `41791234567`.

## Test local

```powershell
venv\Scripts\activate
python app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000/health
```

La réponse ne contient aucun secret.

## Webhook Meta

Callback URL :

```text
https://TON-URL-PUBLIQUE/webhook
```

Verify token : exactement la valeur de `WHATSAPP_VERIFY_TOKEN`.

Le webhook doit être publiquement accessible en HTTPS. Pour un test local, un tunnel HTTPS temporaire peut être utilisé.

## Sécurité

Le bot refuse tous les expéditeurs si `WHATSAPP_ALLOWED_NUMBERS` est vide.

Ne jamais publier :

```text
.env
credentials.json
token.json
bot_state.db
whatsapp_state.db
```
