# Garmin-Sync für Trainingslog

Zieht deine eigenen Garmin-Daten (Workouts **und** Recovery: Schlaf, HRV, Ruhepuls,
Body Battery, Stress, Schritte, Training Readiness) automatisch über GitHub Actions
und legt sie unter [`../garmin/`](../garmin/) ab:

- `garmin/data.json` — maschinenlesbar (auch für die Trainingslog-App)
- `garmin/wellness/JJJJ-MM-TT.md` — eine Klartext-Notiz pro Tag
- `garmin/workouts/JJJJ-MM-TT-*.md` — eine Notiz pro Workout

**Read-only:** Es wird nie etwas zu deinem Garmin-Konto zurückgeschrieben.

---

## Einrichtung (einmalig)

### 1. Secrets anlegen
GitHub → dein Repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Lege drei an (Werte niemals in Chats/Code):

| Name | Wert |
|------|------|
| `GARMIN_EMAIL` | deine Garmin-Connect-E-Mail |
| `GARMIN_PASSWORD` | dein Garmin-Passwort |
| `GH_PAT` | Fine-grained Personal Access Token, **nur dieses Repo**, Rechte **Secrets: Read and write** + **Contents: Read and write** |

Den `GH_PAT` erstellst du unter GitHub → **Settings (dein Profil)** → **Developer settings** →
**Personal access tokens** → **Fine-grained tokens**. Er wird nur einmal zum Speichern des
Login-Tokens gebraucht und darf danach gelöscht werden.

### 2. Einmaliger Login
Actions → **Garmin Auth (einmalig)** → **Run workflow**.
- Hat dein Konto **2FA**? Dann trage den 6-stelligen Code ins Feld `mfa_code` ein.
- Kein 2FA? Feld leer lassen.

Der Workflow speichert danach automatisch das Secret `GARMIN_TOKENSTORE`. Ab jetzt ist
kein Passwort/2FA mehr nötig.

### 3. Test (letzte 3 Tage)
Actions → **Garmin Sync (täglich)** → **Run workflow** → `days` = `3`.
Danach findest du die Ergebnisse unter [`../garmin/`](../garmin/).

### 4. Automatik
Der Sync läuft danach **täglich** (Standard: 05:00 UTC ≈ 07:00 MESZ), siehe
`.github/workflows/garmin-sync.yml`. Uhrzeit über den `cron`-Wert anpassbar.

> **Hinweis (GitHub):** Der geplante (`schedule`) Lauf startet erst, wenn die Workflow-Dateien
> im **Standard-Branch** liegen (also nach dem Merge des Pull Requests). Zum Testen vorher kann
> „Run workflow" auf dem Feature-Branch ausgeführt werden.

---

## Wenn der Sync fehlschlägt

Bei einem Fehlschlag legt der Workflow automatisch ein Issue **„Garmin-Sync fehlgeschlagen"** an
(bzw. kommentiert das offene) — GitHub schickt dazu eine Mail.

**Symptom im Log:**
```
GarminConnectConnectionError: API Error 401
GarminConnectAuthenticationError: Failed to retrieve social profile
```

**Ursache:** Der gespeicherte Garmin-Token ist abgelaufen. Er hält **keine ~1 Jahr**, sondern in
der Praxis nur wenige Wochen: der Tokenstore enthält lediglich `di_token` (~1 h gültig) und einen
`di_refresh_token`, und Garmin gibt bei jedem Refresh einen **neuen** Refresh-Token zurück.

**Das sollte sich normalerweise von selbst erledigen** — der Sync-Workflow schreibt den erneuerten
Token nach jedem Lauf ins Secret `GARMIN_TOKENSTORE` zurück (Schritt „Erneuerten Token zurück ins
Secret schreiben"), und falls der Token doch einmal tot ist, loggt sich `connect_with_token()`
automatisch mit `GARMIN_EMAIL`/`GARMIN_PASSWORD` neu ein.

**Manuell eingreifen** muss man nur, wenn beides scheitert (z. B. Passwort geändert, 2FA neu
aktiviert):

1. Actions → **Garmin Auth (einmalig)** → *Run workflow* (2FA-Code nur falls Garmin danach fragt).
2. Actions → **Garmin Sync (täglich)** → *Run workflow* mit `days` = Anzahl der verpassten Tage.

### `GH_PAT` abgelaufen

Zeigt das Log `failed to fetch public key: HTTP 401: Bad credentials`, ist das Secret `GH_PAT`
abgelaufen. Der Sync **läuft dann trotzdem weiter** (Passwort-Fallback), aber der erneuerte Token
kann nicht mehr gespeichert werden — also bitte erneuern:

Ein neues [Personal Access Token](https://github.com/settings/tokens) mit `repo`-Scope erzeugen und
unter *Settings → Secrets and variables → Actions* als `GH_PAT` hinterlegen. PATs mit Ablaufdatum
müssen regelmäßig erneuert werden; „No expiration" erspart das.

> Historie: Genau dieser Ausfall trat vom 31.07.–03.08.2026 auf, weil der rotierte Token damals
> nur im temporären Runner-Verzeichnis landete und nie ins Secret zurückgeschrieben wurde.

## Lokal ausführen (optional)
```bash
pip install -r garmin-ai/requirements.txt
export GARMIN_EMAIL=... GARMIN_PASSWORD=...
python garmin-ai/garmin_sync.py --auth      # einmalig, erzeugt .garmintoken/
python garmin-ai/garmin_sync.py --days 3    # Sync
```
