#!/usr/bin/env python3
"""
Garmin → Repo Sync (read-only).

Zieht die eigenen Garmin-Connect-Daten (Workouts + Recovery/Wellness) und legt sie
als Klartext-Markdown-Notizen plus eine data.json unter garmin/ ab. Es wird NIE
etwas zu Garmin zurückgeschrieben — ausschließlich lesende Aufrufe.

Zwei Modi:
  python garmin_sync.py --auth
      Einmaliger Login (E-Mail/Passwort aus Umgebung, 2FA-Code optional aus
      GARMIN_MFA). Speichert den langlebigen Garth-Token nach GARMIN_TOKENSTORE_DIR.
      Danach sind keine Zugangsdaten mehr nötig.

  python garmin_sync.py --days N
      Synchronisiert die letzten N Tage. Nutzt den gespeicherten Token aus
      GARMIN_TOKENSTORE_DIR (kein Passwort/2FA nötig). Idempotent: bereits
      vorhandene Tage werden sauber überschrieben.

Umgebungsvariablen:
  GARMIN_EMAIL, GARMIN_PASSWORD   nur für --auth
  GARMIN_MFA                      optionaler 2FA-Code (nur für --auth, falls Garmin fragt)
  GARMIN_TOKENSTORE_DIR           Verzeichnis für den Token (Default: ./.garmintoken)
  GARMIN_OUTDIR                   Ausgabeordner (Default: garmin)
"""
import argparse
import base64
import datetime as dt
import json
import os
import sys

def _Garmin():
    """Importiert die Bibliothek erst bei Bedarf (so klappt --help auch ohne Installation)."""
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("Bitte zuerst Abhängigkeiten installieren: pip install -r garmin-ai/requirements.txt")
    return Garmin


TOKENSTORE = os.environ.get("GARMIN_TOKENSTORE_DIR", ".garmintoken")
OUTDIR = os.environ.get("GARMIN_OUTDIR", "garmin")

MONATE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


# ── Auth ────────────────────────────────────────────────────────────────────
def do_auth():
    """Einmaliger Login, speichert den Token. Behandelt 2FA, falls Garmin danach fragt."""
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        sys.exit("GARMIN_EMAIL und GARMIN_PASSWORD müssen gesetzt sein (als GitHub Secrets).")
    mfa = os.environ.get("GARMIN_MFA", "").strip()
    Garmin = _Garmin()

    # python-garminconnect 0.3.x: Login über self.client; 2FA via return_on_mfa + resume_login.
    api = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        result = api.login()
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "429" in msg or "too many" in msg:
            sys.exit("Garmin hat die Server-IP kurz gedrosselt (429). Bitte ~30–60 Min warten "
                     "und den Workflow erneut starten.")
        raise

    state = result[0] if isinstance(result, tuple) else None
    if state == "needs_mfa":
        if not mfa:
            sys.exit("Garmin verlangt einen 2FA-Code. Workflow erneut starten und den Code "
                     "ins Feld 'mfa_code' eintragen.")
        api.resume_login(result[1], mfa)

    # Token speichern (0.3.x: self.client.dump schreibt die Token-Dateien ins Verzeichnis).
    os.makedirs(TOKENSTORE, exist_ok=True)
    api.client.dump(TOKENSTORE)
    print(f"✓ Login erfolgreich. Token gespeichert unter {TOKENSTORE}/")


def connect_with_token():
    """Verbindet mit gespeichertem Token — ohne Passwort/2FA."""
    if not os.path.isdir(TOKENSTORE) or not os.listdir(TOKENSTORE):
        sys.exit(f"Kein Token unter {TOKENSTORE}. Zuerst 'garmin-auth' ausführen.")
    api = _Garmin()()
    api.login(TOKENSTORE)
    return api


# ── Kleine, robuste Helfer ──────────────────────────────────────────────────
def safe(fn, *args):
    """Ruft eine Garmin-Methode auf; gibt None statt einer Exception zurück."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 — ein fehlendes Feld darf den Lauf nicht abbrechen
        print(f"  · {getattr(fn, '__name__', fn)} übersprungen ({e})")
        return None


def g(d, *keys, default=None):
    """Verschachtelter .get()-Zugriff, tolerant gegenüber fehlenden Ebenen."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def h_m(seconds):
    if not seconds:
        return None
    m = int(seconds) // 60
    return f"{m // 60}h {m % 60:02d}m"


def hours(seconds):
    return round(seconds / 3600, 1) if seconds else None


# ── Datenabruf pro Tag ──────────────────────────────────────────────────────
_DEBUG_DONE = False


def collect_day(api, date):
    global _DEBUG_DONE
    iso = date.isoformat()
    print(f"→ Wellness {iso}")
    summary = safe(api.get_user_summary, iso) or {}
    sleep = safe(api.get_sleep_data, iso) or {}
    hrv = safe(api.get_hrv_data, iso) or {}
    readiness = safe(api.get_training_readiness, iso) or []

    if os.environ.get("GARMIN_DEBUG") and not _DEBUG_DONE:
        _DEBUG_DONE = True
        def dump(name, obj):
            print(f"--- DEBUG {name} ({iso}) ---")
            print(json.dumps(obj, ensure_ascii=False, default=str)[:1200])
        dump("user_summary", summary)
        dump("sleep", sleep)
        dump("hrv", hrv)
        dump("rhr", safe(api.get_rhr_day, iso))
        dump("stress", safe(api.get_stress_data, iso))
        dump("body_battery", safe(api.get_body_battery, iso, iso))
        dump("steps", safe(api.get_steps_data, iso))
        dump("training_readiness", readiness)
        print("--- DEBUG ENDE ---")

    sleep_dto = g(sleep, "dailySleepDTO", default={}) or {}
    tr = (readiness[0] if isinstance(readiness, list) and readiness else readiness) or {}

    day = {
        "sleep": {
            "score": g(sleep_dto, "sleepScores", "overall", "value"),
            "durationH": hours(g(sleep_dto, "sleepTimeSeconds")),
            "deepH": hours(g(sleep_dto, "deepSleepSeconds")),
            "remH": hours(g(sleep_dto, "remSleepSeconds")),
            "awakeH": hours(g(sleep_dto, "awakeSleepSeconds")),
        },
        "hrv": {
            "lastNightAvg": g(hrv, "hrvSummary", "lastNightAvg"),
            "status": g(hrv, "hrvSummary", "status"),
        },
        "restingHR": summary.get("restingHeartRate"),
        "bodyBattery": {
            "high": summary.get("bodyBatteryHighestValue"),
            "low": summary.get("bodyBatteryLowestValue"),
        },
        "stress": {"avg": summary.get("averageStressLevel")},
        "steps": summary.get("totalSteps"),
        "trainingReadiness": {
            "score": tr.get("score") if isinstance(tr, dict) else None,
            "level": tr.get("level") if isinstance(tr, dict) else None,
        },
    }
    return iso, day


def collect_workouts(api, start, end):
    print(f"→ Workouts {start} … {end}")
    acts = safe(api.get_activities_by_date, start.isoformat(), end.isoformat()) or []
    out = []
    for a in acts:
        dur_s = a.get("duration") or 0
        out.append({
            "id": a.get("activityId"),
            "date": (a.get("startTimeLocal") or "")[:10],
            "type": g(a, "activityType", "typeKey") or "unbekannt",
            "name": a.get("activityName"),
            "durationMin": round(dur_s / 60) if dur_s else None,
            "avgHr": a.get("averageHR"),
            "maxHr": a.get("maxHR"),
            "distanceKm": round((a.get("distance") or 0) / 1000, 2) if a.get("distance") else None,
            "calories": a.get("calories"),
        })
    return out


# ── Markdown-Ausgabe (Klartext, eine Notiz pro Tag/Workout) ─────────────────
def date_label(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d}. {MONATE[m]} {y}"


def write_wellness_md(iso, day, folder):
    L = [f"# Erholung — {date_label(iso)}", ""]
    s = day["sleep"]
    if s.get("durationH"):
        det = []
        if s.get("deepH") is not None:
            det.append(f"Tief {s['deepH']}h")
        if s.get("remH") is not None:
            det.append(f"REM {s['remH']}h")
        if s.get("awakeH") is not None:
            det.append(f"wach {s['awakeH']}h")
        score = f" (Score {s['score']}/100)" if s.get("score") is not None else ""
        L.append(f"- Schlaf: {s['durationH']}h{score}" + (f" — {', '.join(det)}" if det else ""))
    if day["hrv"].get("lastNightAvg") is not None:
        st = f" — Status: {day['hrv']['status']}" if day["hrv"].get("status") else ""
        L.append(f"- HRV (letzte Nacht Ø): {day['hrv']['lastNightAvg']} ms{st}")
    if day.get("restingHR") is not None:
        L.append(f"- Ruhepuls: {day['restingHR']} bpm")
    bb = day["bodyBattery"]
    if bb.get("high") is not None or bb.get("low") is not None:
        L.append(f"- Body Battery: Tief {bb.get('low')} → Hoch {bb.get('high')}")
    if day["stress"].get("avg") is not None:
        L.append(f"- Stress: Ø {day['stress']['avg']}")
    if day.get("steps") is not None:
        L.append(f"- Schritte: {day['steps']:,}".replace(",", "."))
    tr = day["trainingReadiness"]
    if tr.get("score") is not None:
        lvl = f" ({tr['level']})" if tr.get("level") else ""
        L.append(f"- Training Readiness: {tr['score']}/100{lvl}")
    if len(L) == 2:
        L.append("_Keine Wellness-Daten für diesen Tag verfügbar._")
    (folder / f"{iso}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def write_workout_md(w, folder):
    slug = (w.get("type") or "workout").replace("/", "-")
    fname = f"{w['date']}-{slug}-{w['id']}.md"
    L = [f"# Workout — {date_label(w['date'])}", "", f"- Sportart: {w['type']}"]
    if w.get("name"):
        L.append(f"- Name: {w['name']}")
    if w.get("durationMin") is not None:
        L.append(f"- Dauer: {w['durationMin']} min")
    if w.get("distanceKm") is not None:
        L.append(f"- Distanz: {w['distanceKm']} km")
    if w.get("avgHr") is not None:
        L.append(f"- Ø-Herzfrequenz: {w['avgHr']} bpm" + (f" (max {w['maxHr']})" if w.get("maxHr") else ""))
    if w.get("calories") is not None:
        L.append(f"- Kalorien: {w['calories']} kcal")
    (folder / fname).write_text("\n".join(L) + "\n", encoding="utf-8")


# ── Hauptlauf ───────────────────────────────────────────────────────────────
def do_sync(days):
    from pathlib import Path
    api = connect_with_token()

    out = Path(OUTDIR)
    wellness_dir = out / "wellness"
    workouts_dir = out / "workouts"
    for p in (wellness_dir, workouts_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Bestehende data.json einlesen (Merge → idempotent)
    data_path = out / "data.json"
    data = {"days": {}, "workouts": []}
    if data_path.exists():
        try:
            data = json.loads(data_path.read_text(encoding="utf-8"))
            data.setdefault("days", {})
            data.setdefault("workouts", [])
        except Exception:
            pass

    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)

    # Wellness pro Tag
    for i in range(days):
        d = start + dt.timedelta(days=i)
        iso, day = collect_day(api, d)
        data["days"][iso] = day
        write_wellness_md(iso, day, wellness_dir)

    # Workouts im Zeitraum (per id zusammenführen)
    fresh = collect_workouts(api, start, today)
    by_id = {w["id"]: w for w in data["workouts"] if w.get("id")}
    for w in fresh:
        if w.get("id"):
            by_id[w["id"]] = w
        write_workout_md(w, workouts_dir)
    data["workouts"] = sorted(by_id.values(), key=lambda w: (w.get("date") or ""), reverse=True)

    data["generated"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✓ Fertig. {days} Tag(e) Wellness, {len(fresh)} Workout(s) im Zeitraum.")
    print(f"  Geschrieben nach {out}/ (data.json, wellness/, workouts/).")


def main():
    ap = argparse.ArgumentParser(description="Garmin → Repo Sync (read-only).")
    ap.add_argument("--auth", action="store_true", help="Einmaliger Login, Token speichern.")
    ap.add_argument("--days", type=int, default=3, help="Anzahl Tage rückwirkend (Default 3).")
    args = ap.parse_args()

    if args.auth:
        do_auth()
    else:
        do_sync(max(1, args.days))


if __name__ == "__main__":
    main()
