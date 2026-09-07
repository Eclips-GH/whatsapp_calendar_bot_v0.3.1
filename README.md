# WhatsApp Calendar Bot — V0.3.1

V0.3 ajoute la recherche, la modification et la suppression d'événements sur Google Calendar et Apple/iCloud.

## Déjà disponible

- lecture de tous les calendriers Google ;
- lecture de tous les calendriers Apple/iCloud ;
- provenance affichée pour chaque événement ;
- création dans un calendrier précis ;
- recherche par titre ;
- suppression ;
- renommage ;
- déplacement de date/heure ;
- gestion des ambiguïtés par choix numéroté.

## Commandes

### Lire

```text
calendriers
calendriers modifiables
aujourd'hui
demain
```

### Rechercher

```text
Cherche Dentiste
Cherche Anniv Osiris
Cherche Réunion dans Google PRO
```

La recherche regarde par défaut les 30 derniers jours et les 365 prochains jours.

### Créer

```text
Ajoute Dentiste demain à 14h dans Google Travail
Ajoute Restaurant samedi à 19h pendant 2h dans Apple César
Ajoute Réunion le 10/09/2026 de 09h30 à 11h dans Google PRO
```

### Supprimer

```text
Supprime Test Bot
Supprime Test Bot demain
Supprime Test Bot dans Google Travail
```

### Renommer

```text
Renomme Test Bot en Dentiste
Renomme Test Bot en Dentiste dans Apple César
```

### Déplacer

Conserve automatiquement la durée originale de l'événement.

```text
Déplace Dentiste à 16h
Déplace Dentiste demain à 16h
Déplace Dentiste le 12/09/2026 à 09h30
```

## Ambiguïtés

Si plusieurs événements correspondent :

```text
J'ai trouvé 2 événements correspondants :
1. Test Bot — 08.09.2026 14:00 [Google • Travail]
2. Test Bot — 08.09.2026 15:00 [Apple • César]

Réponds simplement avec le numéro, ou « annule ».
```

Le choix en attente est enregistré dans `bot_state.db`, donc il fonctionne aussi entre deux exécutions séparées en PowerShell. L'état expire après 30 minutes.

## Limites V0.3

Pour éviter les suppressions accidentelles d'une série entière, la modification/suppression des événements Apple récurrents est volontairement bloquée dans cette version.

Le déplacement horaire d'un événement « toute la journée » est également bloqué pour le moment.

## Mise à jour depuis V0.2

Utilise le ZIP **UPDATE** et extrais-le directement dans ton dossier V0.2 en acceptant le remplacement des fichiers de code.

**Ne supprime pas ton dossier actuel.**

Ces fichiers doivent rester intacts :

```text
.env
credentials.json
token.json
venv/
```

Aucune nouvelle dépendance Python n'est nécessaire pour V0.3. SQLite est inclus dans Python.

## Tests conseillés

Recherche :

```powershell
python -c "from services.command_router import handle_command; print(handle_command('Cherche Test Bot'))"
```

Renommage :

```powershell
python -c "from services.command_router import handle_command; print(handle_command('Renomme Test Bot en Test Bot V03'))"
```

Déplacement :

```powershell
python -c "from services.command_router import handle_command; print(handle_command('Déplace Test Bot V03 demain à 16h'))"
```

Suppression :

```powershell
python -c "from services.command_router import handle_command; print(handle_command('Supprime Test Bot V03'))"
```

Si plusieurs résultats apparaissent, exécute ensuite par exemple :

```powershell
python -c "from services.command_router import handle_command; print(handle_command('2'))"
```

## Secrets

Ne jamais publier :

- `.env`
- `credentials.json`
- `token.json`
- `venv/`
- `bot_state.db`


## V0.3.1 — transfert entre calendriers

Exemples :

```text
Déplace Dentiste vers Apple César
Transfère Dentiste vers Google Travail
Déplace Dentiste demain à 16h vers Apple César
```

Le transfert inter-calendriers conserve le titre, la date, l’heure et la durée.
Les événements récurrents et les événements « toute la journée » ne sont pas
transférés dans cette version pour éviter une modification destructive.
