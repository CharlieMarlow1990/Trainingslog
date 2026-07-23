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
import random
import sys
import time

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
# Drosselung + Retry/Backoff: der Sync macht inzwischen pro Aktivität einen
# zusätzlichen Detail-Call (HF-Verlauf) — ohne Pause zwischen den Requests und
# Rückversuche bei 429 droht Garmin die IP zu drosseln (siehe do_auth()).
REQUEST_DELAY = float(os.environ.get("GARMIN_REQUEST_DELAY", "0.4"))  # Sek. Pause nach jedem Call
MAX_RETRIES = int(os.environ.get("GARMIN_MAX_RETRIES", "4"))
BACKOFF_BASE = float(os.environ.get("GARMIN_BACKOFF_BASE", "2.0"))    # Sek., verdoppelt sich je Versuch


def _is_rate_limited(exc):
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate limit" in msg


def safe(fn, *args):
    """Ruft eine Garmin-Methode auf: drosselt zwischen Aufrufen und versucht
    bei 429/Rate-Limit mit exponentiellem Backoff (+ Jitter) erneut. Gibt am
    Ende None statt einer Exception zurück, statt den ganzen Lauf abzubrechen."""
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = fn(*args)
            if REQUEST_DELAY > 0:
                time.sleep(REQUEST_DELAY)
            return result
        except Exception as e:  # noqa: BLE001 — ein fehlendes Feld darf den Lauf nicht abbrechen
            last_exc = e
            if _is_rate_limited(e) and attempt < MAX_RETRIES:
                wait = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1)
                print(f"  · {getattr(fn, '__name__', fn)}: gedrosselt (429), warte {wait:.1f}s "
                      f"(Versuch {attempt + 1}/{MAX_RETRIES}) …")
                time.sleep(wait)
                continue
            break
    print(f"  · {getattr(fn, '__name__', fn)} übersprungen ({last_exc})")
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
def _rhr_value(rhr):
    """Ruhepuls aus dem dedizierten Endpoint (allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE[0].value)."""
    try:
        m = rhr["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
        return m[0].get("value") if m else None
    except Exception:
        return None


def _body_battery(bb, summary):
    """Body-Battery-Hoch/Tief. Bevorzugt Tageszusammenfassung, sonst Werteliste."""
    high = summary.get("bodyBatteryHighestValue")
    low = summary.get("bodyBatteryLowestValue")
    if high is not None or low is not None:
        return high, low
    try:
        arr = (bb[0].get("bodyBatteryValuesArray") if isinstance(bb, list) and bb else None) or []
        levels = []
        for row in arr:
            # Zeilenformat i.d.R. [timestamp, status, level, version] — Level (0–100) an Index 2
            if isinstance(row, (list, tuple)) and len(row) >= 3 \
                    and isinstance(row[2], (int, float)) and 0 <= row[2] <= 100:
                levels.append(row[2])
        if levels:
            return max(levels), min(levels)
    except Exception:
        pass
    return None, None


def collect_day(api, date):
    iso = date.isoformat()
    print(f"→ Wellness {iso}")
    summary = safe(api.get_user_summary, iso) or {}
    sleep = safe(api.get_sleep_data, iso) or {}
    hrv = safe(api.get_hrv_data, iso) or {}
    rhr = safe(api.get_rhr_day, iso) or {}
    stress = safe(api.get_stress_data, iso) or {}
    bb = safe(api.get_body_battery, iso, iso) or []
    readiness = safe(api.get_training_readiness, iso) or []

    sleep_dto = g(sleep, "dailySleepDTO", default={}) or {}
    tr = (readiness[0] if isinstance(readiness, list) and readiness else readiness) or {}
    bb_high, bb_low = _body_battery(bb, summary)

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
        "restingHR": _rhr_value(rhr),
        "bodyBattery": {"high": bb_high, "low": bb_low},
        "stress": {"avg": stress.get("avgStressLevel")},
        "steps": summary.get("totalSteps"),
        "trainingReadiness": {
            "score": tr.get("score") if isinstance(tr, dict) else None,
            "level": tr.get("level") if isinstance(tr, dict) else None,
        },
    }
    return iso, day


def _hr_series(details):
    """Wandelt die Antwort von get_activity_details() in [{hr, sec}, …] um —
    dasselbe Format, das der clientseitige FIT/GPX-Parser erzeugt (hr =
    Herzfrequenz, sec = Dauer dieses Abschnitts in Sekunden seit dem
    vorherigen Punkt). Gibt None zurück, wenn kein HF-Kanal vorhanden ist."""
    if not isinstance(details, dict):
        return None
    descriptors = details.get("metricDescriptors") or []
    rows = details.get("activityDetailMetrics") or []
    if not descriptors or not rows:
        return None
    hr_idx = ts_idx = None
    for d in descriptors:
        key = (d.get("key") or "")
        idx = d.get("metricsIndex")
        if key == "directHeartRate" or (hr_idx is None and "eartRate" in key):
            hr_idx = idx
        if key == "directTimestamp" or (ts_idx is None and "imestamp" in key):
            ts_idx = idx
    if hr_idx is None:
        return None
    points = []
    for row in rows:
        metrics = row.get("metrics") or []
        if hr_idx >= len(metrics):
            continue
        hr = metrics[hr_idx]
        ts = metrics[ts_idx] if ts_idx is not None and ts_idx < len(metrics) else None
        if hr is None or hr <= 0:
            continue
        points.append((ts, hr))
    if len(points) < 2:
        return None
    series = []
    prev_ts = points[0][0]
    for ts, hr in points[1:]:
        sec = round((ts - prev_ts) / 1000) if ts is not None and prev_ts is not None else 1
        series.append({"hr": round(hr), "sec": max(1, sec)})
        prev_ts = ts
    return series or None


def _power_aggregates(details):
    """Extrahiert Ø-/Max-/Normalized-Power aus get_activity_details() — über
    denselben metricDescriptors/activityDetailMetrics-Mechanismus wie _hr_series
    (Power-Kanal 'directPower'). Dient als Fallback, falls die Aktivitäts-
    Zusammenfassung keine Power-Felder liefert. Gibt {'avg','max','np'} (ints)
    zurück oder None, wenn kein Power-Kanal vorhanden ist."""
    if not isinstance(details, dict):
        return None
    descriptors = details.get("metricDescriptors") or []
    rows = details.get("activityDetailMetrics") or []
    if not descriptors or not rows:
        return None
    pw_idx = None
    for d in descriptors:
        key = (d.get("key") or "")
        idx = d.get("metricsIndex")
        if key == "directPower" or (pw_idx is None and "ower" in key):
            pw_idx = idx
    if pw_idx is None:
        return None
    vals = []
    for row in rows:
        metrics = row.get("metrics") or []
        if pw_idx < len(metrics):
            v = metrics[pw_idx]
            if isinstance(v, (int, float)) and v >= 0:
                vals.append(v)
    if sum(1 for v in vals if v > 0) < 10:
        return None
    avg = round(sum(vals) / len(vals))
    mx = round(max(vals))
    # Normalized Power: 30-Punkt-Rollmittel → 4.-Potenz-Mittel → ^0.25 (Näherung).
    np = None
    if len(vals) >= 30:
        roll = [sum(vals[i - 29:i + 1]) / 30 for i in range(29, len(vals))]
        if roll:
            np = round((sum(p ** 4 for p in roll) / len(roll)) ** 0.25)
    return {"avg": avg, "max": mx, "np": np}


def collect_workouts(api, start, end):
    print(f"→ Workouts {start} … {end}")
    acts = safe(api.get_activities_by_date, start.isoformat(), end.isoformat()) or []
    out = []
    for a in acts:
        dur_s = a.get("duration") or 0
        activity_id = a.get("activityId")
        details = safe(api.get_activity_details, activity_id) if activity_id else None
        # Power: bevorzugt aus der Zusammenfassung, sonst aus dem Detail-Zeitverlauf.
        pw = _power_aggregates(details)
        avg_power = a.get("avgPower")
        max_power = a.get("maxPower")
        norm_power = a.get("normPower") if a.get("normPower") is not None else a.get("normalizedPower")
        if pw:
            if avg_power is None:
                avg_power = pw["avg"]
            if max_power is None:
                max_power = pw["max"]
            if norm_power is None:
                norm_power = pw["np"]
        out.append({
            "id": activity_id,
            "date": (a.get("startTimeLocal") or "")[:10],
            "type": g(a, "activityType", "typeKey") or "unbekannt",
            "name": a.get("activityName"),
            "durationMin": round(dur_s / 60) if dur_s else None,
            "avgHr": a.get("averageHR"),
            "maxHr": a.get("maxHR"),
            "distanceKm": round((a.get("distance") or 0) / 1000, 2) if a.get("distance") else None,
            "calories": a.get("calories"),
            "hrSeries": _hr_series(details),
            "avgPowerW": round(avg_power) if avg_power is not None else None,
            "maxPowerW": round(max_power) if max_power is not None else None,
            "normPowerW": round(norm_power) if norm_power is not None else None,
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
    if w.get("avgPowerW") is not None:
        np = f", NP {w['normPowerW']} W" if w.get("normPowerW") is not None else ""
        L.append(f"- Ø-Leistung: {w['avgPowerW']} W" + (f" (max {w['maxPowerW']})" if w.get("maxPowerW") else "") + np)
    if w.get("calories") is not None:
        L.append(f"- Kalorien: {w['calories']} kcal")
    (folder / fname).write_text("\n".join(L) + "\n", encoding="utf-8")


# ── Hauptlauf ───────────────────────────────────────────────────────────────
def do_sync(days, activities_days=None):
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

    # Workouts im Zeitraum (per id zusammenführen). Für Backfill kann der
    # Aktivitäts-Zeitraum weiter zurückreichen als das Wellness-Fenster.
    act_span = max(days, activities_days or 0)
    act_start = today - dt.timedelta(days=act_span - 1)
    fresh = collect_workouts(api, act_start, today)
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
    ap.add_argument("--days", type=int, default=3, help="Wellness+Aktivitäten rückwirkend (Default 3).")
    ap.add_argument("--activities-days", type=int, default=None,
                    help="Aktivitäten weiter zurück holen (Backfill), unabhängig von --days.")
    args = ap.parse_args()

    if args.auth:
        do_auth()
    else:
        do_sync(max(1, args.days), args.activities_days)


if __name__ == "__main__":
    main()
