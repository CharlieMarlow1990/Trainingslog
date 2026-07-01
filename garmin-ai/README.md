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

## Token abgelaufen?
Der Login-Token gilt ~1 Jahr. Wenn der Sync mit Auth-Fehler abbricht, einfach Schritt 2
(**Garmin Auth**) erneut ausführen.

## Lokal ausführen (optional)
```bash
pip install -r garmin-ai/requirements.txt
export GARMIN_EMAIL=... GARMIN_PASSWORD=...
python garmin-ai/garmin_sync.py --auth      # einmalig, erzeugt .garmintoken/
python garmin-ai/garmin_sync.py --days 3    # Sync
```
