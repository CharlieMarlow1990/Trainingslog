# Paket I — Kraftfokus, Erhaltungsreize, Langzeitverteilung

**Unabhängig von Paket H.** Betrifft ausschließlich die Log-Seite (`Aktuelle Einheiten`) und die Einstellungen. Braucht keine Blöcke, keine Phasen, keine Vorlagen — funktioniert mit den vorhandenen Daten.

**Reihenfolge:** Vor Paket H bauen. Paket I liefert die Fokus-Achse (`cell.kraft.<focus>.count`) und die Anrechnungsmatrix, die Paket H in den Kraftvorlagen und Floors voraussetzt.

**Inhalt**
1. Kraft-Fokus als Session-Attribut (Maximalkraft / Hypertrophie / Kraftausdauer)
2. Erhaltungsfenster je Sportart und Fokus, mit Kreuzanrechnung
3. Sportarten-Übersicht mit Recency, Trend und Popover
4. Langzeitverteilung 28 d gegen 84 d
5. Gesamtzeit-Leiste inkl. nicht-zonenbasierter Sportarten

---

## 1 · Was bereits vorhanden ist

| Vorhanden | Stelle | Rolle |
|---|---|---|
| Sportarten mit `zoneBased`-Flag | `DEFAULT_SPORTS`, `isSportZoneBased` | unverändert |
| `sportMin`, `sportCount` je Sportart | `computeBudgetActuals` | Basis für Ø/Woche |
| `zoneMin`, `zoneCount`, `sportZoneMin` | `computeBudgetActuals` | Basis für Verteilung |
| Wochennormierung | `computeBudgetActuals` (`/weeks`) | Ø/Woche ohne Zusatzrechnung |
| Budget-Panel | `renderBudgetPanel` | wird erweitert |
| Popover-Muster | `openBlockInfoPopover` | Vorlage für (?)-Popover |

**Wichtig:** `Capacity` ist `zoneBased:true` und fließt bereits in die Intensitätsverteilung ein. `Kraft`, `Kampfsport` und `Sonstiges` sind `zoneBased:false` und bleiben außen vor. Diese Trennung bleibt unangetastet — sie ist die Voraussetzung dafür, dass die LIT-Quote nicht durch Krafteinheiten verschoben wird.

---

## 2 · Kraft-Fokus

### 2.1 Konfiguration

```js
cfg.strengthFoci = [
  { key:'max', label:'Maximalkraft',  maintainDays:10 },
  { key:'hyp', label:'Hypertrophie',  maintainDays:14 },
  { key:'ka',  label:'Kraftausdauer', maintainDays:7  }
];
```

Editierbar in den Einstellungen (Label und `maintainDays`; Keys fix). Bei fehlender Config Defaults anlegen wie bei `cfg.zones`.

`maintainDays` sind **Richtwerte, keine Studienwerte** — das muss im Popover so stehen. Belastbare Erhaltungsdaten existieren für Maximalkraft (Erhalt über relative Last, eine Einheit pro Woche, ein Satz je Übung, über Monate). Für Hypertrophie und Kraftausdauer sind die Werte gesetzt, nicht belegt.

### 2.2 Session-Attribut

```sql
alter table sessions add column strength_focus text;   -- 'max'|'hyp'|'ka'|'gemischt'|null
```

Nur relevant für Sportarten mit `zoneBased:false` und Kraftcharakter. Erfassung im Log-Sheet als Auswahlfeld, sichtbar wenn `sport === 'Kraft'`.

**Bestimmungskette:**

```
1  Protokollzuordnung (Paket H)      → gesetzt
2  manuelle Angabe im Log            → gesetzt
3  Vorbelegung aus letzter Kraft-
   einheit desselben Sports          → Vorschlag, überschreibbar
4  null                              → „nicht zugeordnet"
```

Keine automatische Erkennung aus HF oder Dauer — Herzfrequenz sagt über die Last nichts. Bestandsdaten bleiben `null` und werden in der Übersicht als eigene Zeile ausgewiesen, nicht auf `max` verteilt.

### 2.3 Kreuzanrechnung

```js
const STRENGTH_MAINTAINS = {
  max:      { hyp: 1.0, ka: 0.5 },
  hyp:      { max: 0.5, ka: 0.5 },
  ka:       { hyp: 0.5 },
  capacity: { ka:  1.0 }        // Sportart Capacity, nicht Fokus
};
```

| Fokus | wird gehalten durch |
|---|---|
| Maximalkraft | Hypertrophie (0.5) |
| Hypertrophie | Maximalkraft (1.0), Kraftausdauer (0.5) |
| Kraftausdauer | Capacity (1.0), Maximalkraft (0.5), Hypertrophie (0.5) |

**Semantik der Faktoren:**
- `1.0` — Uhr wird zurückgesetzt, als wäre eine dedizierte Einheit absolviert worden
- `0.5` — Fenster wird um 50 % verlängert, Uhr läuft weiter

Ohne diese Unterscheidung würde eine einzige schwere Einheit rechnerisch alle drei Foki gleichzeitig zurücksetzen.

**Bewusst nicht enthalten:** Capacity → Hypertrophie. Muskelmasse wird über mechanische Spannung gehalten; Zirkelformate mit niedriger Last erreichen das bei vorhandenem Kraftniveau nicht.

```js
function effectiveDaysSince(focusKey, sessions, today){
  const direct = daysSinceFocus(focusKey, sessions);
  let best = { days: direct, source: null };
  for(const [srcKey, targets] of Object.entries(STRENGTH_MAINTAINS)){
    const f = targets[focusKey]; if(!f) continue;
    const d = srcKey==='capacity'
      ? daysSinceSport('Capacity', sessions)
      : daysSinceFocus(srcKey, sessions);
    if(d==null) continue;
    if(f===1.0 && d<best.days) best={days:d, source:srcKey};
    // f===0.5 verlängert das Fenster, nicht die Uhr — separat zurückgeben
  }
  return best;   // {days, source}
}
```

Faktor-0.5-Quellen liefern zusätzlich `windowBonus`, das in §3.2 auf `maintainDays` aufgeschlagen wird.

### 2.4 Abgrenzung zu Capacity

`Capacity` bleibt eine eigene Sportart mit `zoneBased:true`. Sie wird **nicht** zu `Kraft` mit `focus:'ka'` aufgelöst.

| | Intensitäts-Slot | KA-Erhaltung | KA-Volumenziel |
|---|---|---|---|
| Capacity | 1.0 (HIT) | 1.0 | 0.5 |
| Kraft, Fokus `ka` | — | 1.0 | 1.0 |

Konsistent mit der bestehenden Regel: eine Einheit belegt einen Intensitäts-Slot und höchstens einen Floor.

**Drift-Hinweis:** Läuft Kraftausdauer über längere Zeit ausschließlich über Capacity, bleibt der Reiz formal bestehen, aber die Last stagniert bei dem, was der Zirkel vorgibt. Ab einer Schwelle (`cfg.derivedMaintainWarnDays`, Default 42) wird der Herkunftspfeil eingefärbt und das Popover ergänzt.

---

## 3 · Erhaltungsfenster je Sportart

### 3.1 Konfiguration

```js
cfg.sportMaintain = {
  Lauf:       5,
  Rad:        9,
  Capacity:   9,
  Kampfsport: 14,
  Sonstiges:  null   // null = keine Prüfung
};
```

Editierbar. Neue Sportarten bekommen `null`.

**Begründung für die Staffelung** (gehört ins Popover, nicht in den Code): Die zentrale Ausdauerkomponente — VO₂max, Herzzeitvolumen, Blutvolumen — wird von jedem Ausdauertraining gehalten. Modalitätsgebunden ist nur das Spezifische: Laufökonomie und mechanische Toleranz beim Laufen, Position und Trittfrequenz beim Radfahren. Deshalb ist das Laufsfenster kürzer als das Radfenster.

Darüber eine eigene Zeile:

```
Ausdauerreiz gesamt      vor 2 d
```

Berechnet über alle Sportarten mit `zoneBased:true`. Ohne sie liest sich „Rad vor 7 Tagen" wie ein Ausdauerdefizit, obwohl nichts fehlt.

### 3.2 Statusstufen

```js
function maintainStatus(days, windowDays, bonus=0){
  if(windowDays==null || days==null) return 'none';
  const w = windowDays * (1 + bonus);
  if(days <= w)        return 'open';
  if(days <= w * 1.5)  return 'over_soft';
  return 'over_hard';
}
```

| Status | Marker |
|---|---|
| `open` | kein Marker |
| `over_soft` | `!` in `--ink2` |
| `over_hard` | `!` in `--accent` |

Zweistufig, damit die Warnung an der Grenze nicht flackert.

---

## 4 · Sportarten-Übersicht

Ersetzt die bestehende Punktreihen-Darstellung (`EINHEITEN JE SPORTART`).

```
SPORTARTEN                   Ø/Wo 28d   Zuletzt
──────────────────────────────────────────────
Ausdauerreiz gesamt                      2 d
Lauf                            3,0      2 d   (?)
Rad                             1,0      1 d   (?)
Capacity                        1,5      4 d   (?)
Kraft                           1,5      5 d   (?) ⌄
  Maximalkraft                  0,5     11 d ! (?)
  Kraftausdauer                 1,0      4 d ↓ (?)
  Hypertrophie                    —     11 d ↓ (?)
  nicht zugeordnet              0,5      –
──────────────────────────────────────────────
```

### 4.1 Spalten

- **Ø/Wo 28d** — `sportCount` aus `computeBudgetActuals(−27d, heute)`, gerundet auf 0,5
- **Zuletzt** — ganze Tage seit der letzten Einheit
- **Marker** — `!` Fenster überschritten, `↓` Erhaltung aus fremder Quelle
- **(?)** — Popover, siehe §4.3

Kein Ampelwort. „Erhalt / Aufbau / Abbau" suggeriert eine Sicherheit, die die Datengrundlage nicht hergibt — insbesondere „Abbau" bleibt ohne Leistungsmessung Vermutung.

### 4.2 Trendpfeil (optional, zweite Ausbaustufe)

Falls die Zeilenbreite es zulässt, zusätzlich `▴ ▬ ▾` aus dem Vergleich **Minuten** 28 d gegen 84 d, Schwelle ±15 %.

Minuten, nicht Einheiten: Steigende Frequenz bei sinkendem Umfang ist kein Aufbau.

### 4.3 Kraft-Unterzeilen

Ausklappbar (Chevron), Default eingeklappt.

**Warnung schlägt nach oben durch:** Ist ein Unterfokus `over_soft` oder `over_hard`, zeigt die Elternzeile `!` mit Zähler, z. B. `! (1)`. Sonst versteckt sich der Abbau hinter dem Chevron.

Zeile `nicht zugeordnet` erscheint nur, wenn Krafteinheiten ohne `strength_focus` im Fenster liegen.

### 4.4 Popover-Inhalte

Grammatik wie `openBlockInfoPopover`. Drei bis vier Zeilen, dann ein Button.

**Lauf**
> Erhaltungsfenster 5 Tage. Betrifft die laufspezifische mechanische Toleranz und Ökonomie. Die zentrale Ausdauerkomponente wird auch durch Rad- und Capacity-Einheiten gehalten.
> Zuletzt vor 2 Tagen · offen
> Richtwert, kein Studienwert.
> `[Fenster anpassen]`

**Rad**
> Erhaltungsfenster 9 Tage. Überwiegend zentrale Anpassung, wenig modalitätsspezifische Struktur — deshalb länger als beim Laufen.
> Zuletzt vor 1 Tag · offen
> `[Fenster anpassen]`

**Maximalkraft**
> Erhaltungsfenster 10 Tage. Maximalkraft wird über die relative Last gehalten, nicht über Volumen — eine Einheit pro Woche mit einem Satz je Übung genügt.
> Zuletzt vor 11 Tagen · Fenster überschritten
> `[Fenster anpassen]`

**Kraftausdauer ↓**
> Erhaltungsfenster 7 Tage.
> Zuletzt vor 4 Tagen — Capacity-Einheit.
> Letzte dedizierte Einheit vor 16 Tagen.
> Capacity setzt den Reiz vollständig, zählt aber nur zur Hälfte auf Volumenziele.
> `[Fenster anpassen]`

**Hypertrophie ↓**
> Erhaltungsfenster 14 Tage.
> Zuletzt vor 5 Tagen — über Maximalkraft gehalten.
> Keine dedizierte Einheit in den letzten 42 Tagen.
> Schwere Lasten halten Muskelmasse mit. Capacity-Einheiten zählen hier nicht.
> `[Fenster anpassen]`

Die Zeile „letzte dedizierte Einheit" erscheint nur, wenn sie sich von der abgeleiteten unterscheidet. Überschreitet sie `cfg.derivedMaintainWarnDays`, wird der `↓`-Pfeil in `--z3` eingefärbt — keine Warnung, aber sichtbar: dauerhaft abgeleitete Erhaltung ist Stagnation auf dem Niveau des Fremdreizes.

`[Fenster anpassen]` schreibt direkt in `cfg.sportMaintain[key]` bzw. `cfg.strengthFoci[i].maintainDays`.

---

## 5 · Langzeitverteilung

Neuer Abschnitt unterhalb der bestehenden Intensitätsverteilung.

```
LANGZEITVERTEILUNG
──────────────────────────────────────
                28 d      84 d
LIT             56 %      71 %   ▾
MIT             17 %      11 %   ▴
HIT             26 %      18 %   ▴
──────────────────────────────────────
LIT-Anteil, 12 Wochen
 ▁▂▃▅▆▆▅▄▂▃▄▅
──────────────────────────────────────
```

### 5.1 Zwei Fenster

```js
const w28 = computeBudgetActuals(addDays(today,-27), today);
const w84 = computeBudgetActuals(addDays(today,-83), today);
```

Pfeil nur bei Abweichung ≥ 3 Prozentpunkte.

| Muster | Bedeutung |
|---|---|
| 28d < 84d bei LIT | Intensität steigt |
| 28d > 84d bei LIT | Rückkehr zum Fundament |
| beide gleich | stabil |

Eine einzelne Prozentzahl sagt nicht, ob die Verteilung driftet. Die Gegenüberstellung zeigt die Richtung ohne zusätzliche Grafik.

### 5.2 Sparkline

LIT-Anteil je Kalenderwoche über 12 Wochen. Zwölf Aufrufe von `computeBudgetActuals` mit Wochenfenstern, oder einmalig aus einer Tagesreihe aggregiert.

Erweiterung, sobald Blöcke existieren (Paket H): Wochen innerhalb eines Blocks in `--ink3` statt `--ink`. Dann ist erkennbar, ob ein LIT-Einbruch geplant war.

### 5.3 Zielmarke

```js
cfg.constraints.litTargetPct = null;   // z.B. 80
```

Nur wenn gesetzt, erscheint eine Marke. Ohne Wert behauptet die App kein Ziel.

---

## 6 · Gesamtzeit-Leiste

Über der bestehenden Intensitätsverteilung, mit **anderem Nenner**.

```
GESAMTZEIT 3:57 h  ·  Ø Woche, rollend 28 Tage
▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒░░░░
Ausdauer 2:32 · Capacity 0:40 · Kraft 0:45

INTENSITÄTSVERTEILUNG — Ausdauer + Capacity, 3:12 h
[bestehende Balken mit Zielmarken]
```

**Kritisch:** Zwei Leisten mit unterschiedlichen Bezugsgrößen, beide beschriftet. Würde Kraft in die LIT/MIT/HIT-Prozente einfließen, wäre die 80-%-Marke bedeutungslos.

Die Beschriftung der zweiten Leiste muss ausweisen, welche Sportarten enthalten sind — `Capacity` ist `zoneBased:true` und zählt mit, was auf den ersten Blick überrascht.

Der bestehende Untertitel `Ø Woche, rollierend 28 Tage` bleibt und gilt für beide Leisten.

---

## 7 · Migration

```sql
-- docs/migrations/2026-08-XX-paket-i.sql
alter table sessions add column strength_focus text;
```

Plus in `cfg` (localStorage, keine Migration):
- `strengthFoci` — drei Einträge mit `maintainDays`
- `sportMaintain` — Objekt je Sportart, Default `null` für unbekannte
- `derivedMaintainWarnDays` — Default 42
- `constraints.litTargetPct` — Default `null`

Alles optional. Ohne Konfiguration verhält sich die Log-Seite wie bisher, ergänzt um die Recency-Spalte (die braucht keine Config).

---

## 8 · Akzeptanzkriterien

**Kraft-Fokus**
- [ ] `strength_focus` im Log-Sheet nur bei Kraft-Sportarten sichtbar
- [ ] Vorbelegung aus der letzten Krafteinheit, überschreibbar
- [ ] Bestandsdaten mit `null` erscheinen als eigene Zeile „nicht zugeordnet"
- [ ] Keine automatische Erkennung aus HF oder Dauer

**Kreuzanrechnung**
- [ ] `1.0`-Quellen setzen die Uhr zurück, `0.5`-Quellen verlängern nur das Fenster
- [ ] Capacity rechnet auf Kraftausdauer (1.0), nicht auf Hypertrophie
- [ ] Herkunft wird als `↓` markiert, nur bei Faktor 1.0
- [ ] `↓` färbt sich in `--z3`, wenn die letzte dedizierte Einheit älter als `derivedMaintainWarnDays` ist
- [ ] Capacity bleibt eigene Sportart mit `zoneBased:true`

**Erhaltungsfenster**
- [ ] Zweistufige Warnung: `over_soft` ab Fenster, `over_hard` ab Fenster × 1.5
- [ ] Keine Prüfung bei `maintainDays === null`
- [ ] Zeile „Ausdauerreiz gesamt" über alle `zoneBased:true`-Sportarten
- [ ] Warnung eines Unterfokus schlägt auf die eingeklappte Kraft-Zeile durch

**Übersicht**
- [ ] Ø/Wo auf 0,5 gerundet
- [ ] Kraft-Unterzeilen ausklappbar, Default eingeklappt
- [ ] Kein Ampelwort („Erhalt/Aufbau/Abbau") in der Tabelle
- [ ] Popover je Zeile mit Fenster, Begründung, Status, Anpassen-Button
- [ ] Popover kennzeichnet die Fenster als Richtwerte

**Langzeitverteilung**
- [ ] 28 d und 84 d nebeneinander, Pfeil ab 3 Prozentpunkten
- [ ] Sparkline über 12 Kalenderwochen
- [ ] Zielmarke nur bei gesetztem `litTargetPct`

**Gesamtzeit**
- [ ] Zwei Leisten mit getrennten Nennern, beide beschriftet
- [ ] Kraft fließt nicht in die LIT/MIT/HIT-Prozente ein
- [ ] Beschriftung nennt die in der Intensitätsverteilung enthaltenen Sportarten

---

## 9 · Schnittstelle zu Paket H

Zwei Stellen, die Paket H aus Paket I bezieht:

1. **Bandachse für Kraft.** `cell_targets` speichert Sport × Achsenwert. Die Achse ist sportabhängig:
   ```js
   isSportZoneBased(sport) ? zone : strengthFocus
   ```
   Damit wird `cell.kraft.max.count` möglich, ohne ein zweites Zielmodell.

2. **Kraft-Floors nutzen die Anrechnungsmatrix.** Ein Floor `strength_heavy ≥ 1/10d` hält über die Kreuzanrechnung automatisch auch Hypertrophie — der Floor braucht einen Eintrag, nicht drei.

Umgekehrt: Ein Floor auf Kraftausdauer wird in HIT-Blöcken mit Capacity-Einheiten faktisch immer erfüllt. Korrekt, sollte aber im Cockpit als `↓` erscheinen, damit nicht der Eindruck dedizierter KA-Arbeit entsteht.

---

## 10 · Offene Entscheidungen

1. **`gemischt` als vierter Fokus.** Sinnvoll für Einheiten mit schwerem Hauptteil und Zusatzvolumen — oder erzeugt es nur eine Kategorie, die alles auffängt und nichts aussagt?
2. **Kampfsport im Erhaltungsmodell.** Aktuell `zoneBased:false` und ohne Fokus. Eigenes Fenster oder ganz außen vor?
3. **Trendpfeil in der Sportarten-Tabelle.** Zeilenbreite auf 480 px prüfen — vier Spalten plus zwei Marker plus (?) könnte zu eng werden. Notfalls Trend nur im Popover.
4. **Sparkline-Berechnung.** Zwölf `computeBudgetActuals`-Aufrufe bei jedem Render, oder einmalig aggregierte Tagesreihe im Speicher?
5. **`maintainDays` für Rad.** 9 Tage ist gesetzt, nicht belegt. Nach ein paar Wochen Nutzung prüfen, ob der Wert zur eigenen Erfahrung passt.
