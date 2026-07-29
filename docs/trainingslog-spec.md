# Trainingslog — Umbau-Spezifikation

Zielsystem: Single-File PWA (`index.html`), Supabase/PostgreSQL, GitHub Pages, GitHub OAuth.
Konventionen: zentrales `DB`-Objekt, Config in `localStorage`, Emojis als HTML-Entities, Theming ausschließlich über CSS-Variablen.

Reihenfolge der Umsetzung: **N → A → B → F → J**
(Refactoring zuerst, weil A und F auf `buildDailyLoadSeries()` und korrektem ACWR aufsetzen.)

---

## Paket N — Refactoring & Metrik-Korrekturen

Vorbedingung für alles Weitere. Kein UI-Sichtbares außer korrigierten Zahlen.

### N1 — `buildDailyLoadSeries()`

Drei verstreute Schleifen, die tägliche Load-Serien aufbauen, in **eine** Funktion konsolidieren.

```js
// buildDailyLoadSeries(sessions, opts) -> Array<{date:'YYYY-MM-DD', load:number, sessions:Session[]}>
// opts: { from, to, includeEmptyDays:true, sportFilter?, statusFilter? }
```

Anforderungen:
- lückenlose Tagesreihe inkl. Ruhetage (`load: 0`, `sessions: []`)
- `statusFilter` default `'done'` — Ghost-Sessions (Paket A) dürfen historische Metriken nicht verfälschen
- alle bestehenden Aufrufstellen auf die neue Funktion umstellen, Duplikate entfernen
- Ergebnis memoisieren (Cache-Key aus `from|to|filter|sessions.length|maxUpdatedAt`)

### N2 — ACWR auf echte rollierende Fenster

Aktuell: Kalenderwochen-Buckets (Mo–So). Das macht wochenübergreifende Lastmuster unsichtbar.

Neu:
- **Acute** = Summe Load Tag *d−6* bis *d* (7 Tage, inkl. heute)
- **Chronic** = Ø Tagesload Tag *d−27* bis *d* × 7 (28 Tage, auf Wochenäquivalent skaliert)
- ACWR = Acute / Chronic
- Für jeden Tag der Serie berechnet, nicht nur für den aktuellen
- Chronic erst ab ≥28 Tagen Datenhistorie ausweisen (volle Chronic-Fensterlänge, `CHRONIC_MIN_HISTORY_DAYS`), sonst `null` + Hinweis „Basis unvollständig"
- Ruhetage zählen in beiden Fenstern als 0 — das ist korrekt und beabsichtigt

Bestehende Kennzahlen „LETZTE 7 TAGE" (645) und „CHRONISCHE LAST Ø letzte 28 Tage" (568) auf dieselbe Berechnung umstellen, damit App-weit ein Wert gilt.

### N3 — Trainingstage-Statistik

Wiederkehrendes Problem: Ruhetage ziehen rollierende Mittelwerte optisch nach unten.

- `buildDailyLoadSeries()` liefert zusätzlich `trainingDaysOnly` als abgeleitete Serie
- Alle Charts, die einen *typischen Trainingsumfang* zeigen (EF, Workload-Punkte, Wochenvergleich), nutzen die Trainingstag-Serie
- Alle Charts, die *Belastungsdichte* zeigen (ACWR, CTL/ATL, Monotonie), nutzen die volle Tagesreihe inkl. Ruhetagen
- Im Chart-Untertitel jeweils ausweisen, welche Basis verwendet wurde

### N4 — Vorbereitung Recovery Pressure

Nur Datenpfad, keine UI:
- `computeMonotonyStrain()` auf `buildDailyLoadSeries()` umstellen
- `recoveryFactor` (number, default 1.0) pro Zone in `cfg.sportZones` ergänzen, inkl. Migration bestehender localStorage-Configs mit Default-Wert
- Load-Streak (aufeinanderfolgende Tage mit Load > 0) und Recovery-Debt (Summe fehlender Ruhetage im 14-Tage-Fenster) als reine Berechnungsfunktionen bereitstellen

---

## Paket A — Ghost-Sessions

Geplante und absolvierte Einheiten sind **derselbe Objekttyp in verschiedenen Zuständen**.

### A1 — Schema

```sql
alter table sessions
  add column if not exists status text not null default 'done'
    check (status in ('planned','done')),
  add column if not exists planned_ref uuid references sessions(id) on delete set null,
  add column if not exists block_id uuid;  -- siehe Paket F

create index if not exists sessions_status_date_idx on sessions (status, date);
```

Fallback-Regel (bestehende Konvention): Inserts müssen ohne die neuen Spalten durchlaufen, falls die Migration noch nicht ausgeführt wurde; Constraint-Fehler lesbar an die UI durchreichen.

`DB`-Erweiterungen:
- `getSessions({status})` — default `'done'`
- `addPlannedSession(payload)`
- `movePlannedSession(id, newDate)`
- `linkPlannedToDone(plannedId, doneId)`

### A2 — Anlegen per Long-Press

- Long-Press (≥400 ms) auf leere Kalenderzelle → Halbmodal von unten
- Vier Buttons in Sportfarben: Rad / Lauf / Kraft / Capacity
- Tap legt sofort an, **kein Formular, kein Speichern-Button**
- Defaults aus Median der letzten fünf abgeschlossenen Einheiten derselben Sportart (Dauer, Zone). Fallback bei <3 Einheiten: 60 min, Z2.
- Undo-Toast für 5 Sekunden

### A3 — Rendering

| Zustand | Darstellung |
|---|---|
| `planned` | `border: 1.5px dashed`, `opacity: .55`, keine Füllung, Sportfarbe |
| `done` | gefüllt, Sportfarbe, wie bisher |
| gekoppelt | gefüllter Block + darüber dünne Plan-Ist-Zeile |

Ghosts sind in **allen** Auswertungen ausgeschlossen, solange sie `planned` sind (siehe N1 `statusFilter`).

### A4 — Drag zwischen Tagen

- Long-Press hebt den Block an: `transform: scale(1.04) rotate(-.6deg)`, weicher Schatten
- Pointer-Events (`pointerdown`/`move`/`up`), `touch-action: none` am Block, damit Scroll nicht konkurriert
- Drop-Targets: Tageszellen bekommen beim Überfahren hellen Rahmen, Snapping auf Tagesmitte
- Drop auf linken Bildschirmrand (< 40 px) = löschen, mit Undo-Toast
- Drop auf belegten Tag = beide Einheiten liegen als Doppel im Tag

### A5 — Live-Load-Band beim Ziehen

Während des Drags am oberen Bildschirmrand ein schmales fixiertes Band:

```
7T-Load 645 → 712 · ACWR 1.14 → 1.25
```

- Berechnung gegen eine hypothetische Serie: bestehende Sessions + Ghosts, wobei der gezogene Ghost auf dem aktuellen Hover-Tag liegt
- Ghosts zählen **nur in dieser Projektion**, nicht in den regulären Kennzahlen
- Farbwechsel bei ACWR > 1.3 (Warnton) und < 0.8 (gedämpft)
- Throttle auf `requestAnimationFrame`, keine Neuberechnung pro Pixel

### A6 — Kopplung beim Garmin-Import

Beim Import einer neuen Session (FIT/GPX/TCX):
1. Suche `planned`-Sessions derselben Sportart im Fenster ±1 Tag
2. Bei genau einem Treffer: automatisch koppeln (`done.planned_ref = planned.id`), Ghost bleibt als Referenz erhalten, wird aber nicht mehr eigenständig gerendert
3. Bei mehreren Treffern: in der Import-Tabelle ein Auswahlfeld anbieten
4. Bei keinem Treffer: Session ohne Kopplung anlegen

Der Ghost wird **nie überschrieben oder gelöscht** — die Differenz ist der eigentliche Datenwert.

### A7 — Plan-Ist-Anzeige

Im gekoppelten Tag über dem Block eine dünne Zeile:

```
geplant 60 min Z2 · gelaufen 78 min, 41% Z3
```

Abweichungen ab ±20 % Dauer oder ±15 Prozentpunkten Zonenanteil visuell hervorheben.

### A8 — Plan-Ist-Differenz als Metrik

Bereitstellen (Anzeige folgt in einem späteren Paket):
- `deltaDuration`, `deltaLoad`, `deltaZoneDistribution` pro gekoppeltem Paar
- Ausfallquote: Anteil `planned`-Sessions ohne Kopplung, deren Datum in der Vergangenheit liegt, aggregierbar nach Wochentag und Sportart

---

## Paket B — Horizontale Sektionen

**Leitprinzip:** vertikal = anderes Thema, horizontal = andere Perspektive auf dasselbe Thema. Ausnahmslos.

### B1 — Generische Mechanik

Ein wiederverwendbares Muster, kein Einzelfall pro Sektion:

```css
.hswipe { display:flex; overflow-x:auto; scroll-snap-type:x mandatory;
          scrollbar-width:none; -webkit-overflow-scrolling:touch; }
.hswipe::-webkit-scrollbar { display:none; }
.hswipe > * { flex:0 0 100%; scroll-snap-align:center; }
```

- Dot-Indicator unterhalb jeder Sektion, aktiver Index über `Math.round(scrollLeft / clientWidth)` im gedrosselten `scroll`-Handler
- Erster Aufruf einer Sektion: kurzer Peek-Hint (Inhalt ~12 px verschoben, federt zurück), einmalig pro Sektion in `localStorage` gemerkt
- Slot-Inhalte lazy rendern: Chart eines Slots erst zeichnen, wenn er sichtbar wird

### B2 — Log, Sektion „Aktuelle Einheiten" (3 Slots)

**Slot 1 — Liste.** Wie bisher.

**Slot 2 — Budget.**
- Ein horizontaler Balken, 100 % Breite = Wochenvolumen-Ziel; Segmente in Sportfarben, gestrichelter Rest = offen
- Darunter zwei Zeilen:
  - `LIT 82% / Ziel 80%`
  - `HIT 18% / Ziel 20% — davon Capacity 60%, Kraft 40%`
- **Berechnungsbasis: rollierende 28 Tage**, nicht die laufende Woche (sonst montags immer 0 %)
- Zonenzuordnung: Z1+Z2 → LIT, Z3 → separat ausweisen (Grauzone), Z4+Z5 → HIT

**Slot 3 — Nächste geplante Einheiten.** Die drei nächsten Ghosts als Zeilen mit Countdown. Leerzustand mit direktem Link in den Kalender.

### B3 — Auswertung, Karte „Aerobe Effizienz" (3 Slots)

- **Slot 1:** EF über Zeit mit Median-±MAD-Band (Bestand)
- **Slot 2:** EF gegen Load auf der X-Achse, gleiches Zeitfenster — klärt, ob EF-Rückgang ermüdungsgetrieben ist oder Streuung
- **Slot 3:** Rad und Lauf übereinander, je auf den ersten Wert des Fensters normalisiert (Index 100)

### B4 — Kalender-Kopfzeile

Horizontales Swipen der Kopfzeile wechselt die Auflösung: Monat ← → Quartal ← → Jahr. Details in Paket F.

---

## Paket F — Blöcke

Zeitspannen mit Intention. Machen die Periodisierung sichtbar, die bisher nur implizit existiert.

### F1 — Schema

```sql
create table if not exists blocks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text not null,
  intention text not null check (intention in ('LIT','MIT','HIT','Deload','Frei')),
  starts_on date not null,
  ends_on date not null,
  color text,
  note text,
  created_at timestamptz default now()
);
create index if not exists blocks_range_idx on blocks (user_id, starts_on, ends_on);
```

`sessions.block_id` (aus A1) wird **abgeleitet, nicht gespeichert-fixiert**: die Zuordnung ergibt sich aus dem Datum. `block_id` dient nur als Cache und wird bei Blockänderung neu berechnet. Überlappende Blöcke sind zulässig; bei Mehrfachtreffer gewinnt der kürzere Block.

### F2 — Anlegen

- Im Quartals- oder Jahresmodus: Button „Block anlegen" → Start-/Enddatum über Tap auf zwei Wochenzeilen
- Alternativ Zwei-Finger-Drag über mehrere Wochenzeilen
- Felder: Titel, Intention, Farbe, Notiz
- Kanten nachträglich per Drag verschiebbar (Snapping auf Wochengrenzen)

### F3 — Rendering

- Getönte Hinterlegung **hinter** den Zellen, kein eigenes Element im Vordergrund
- Bestehendes Grain-Muster als Textur, Kanten leicht unregelmäßig (SVG-`feTurbulence`-Maske oder vorgerendertes PNG-Tile)
- Titel dezent an der linken Oberkante, nur wenn Blockbreite es zulässt
- Im Monatsmodus: Hinterlegung über die betroffenen Tageszellen hinweg
- Im Quartals-/Jahresmodus: durchgehender Balken

### F4 — Auflösungsstufen

Dieselben Objekte, andere Auflösung — **keine getrennten Datensätze**:

| Stufe | Darstellung |
|---|---|
| Monat | Tageszellen mit Sessions + Ghosts, Blöcke als Hinterlegung |
| Quartal | eine Zeile pro Woche, gestapelter Balken nach Modalität, Blockhinterlegung. Planungsebene für Blöcke. |
| Jahr | zwölf Zeilen, nur Blöcke und Anker, keine Einzeleinheiten |

Ein im Quartalsmodus aufgezogener Block erscheint sofort im Monatsmodus als Hinterlegung.

### F5 — Auswertungsfilter

- In der Auswertung ein Filter-Chip „nur dieser Block" (Blockauswahl über Dropdown)
- Alle Charts respektieren den Filter, indem `buildDailyLoadSeries()` mit `from`/`to` des Blocks aufgerufen wird
- Zusätzlich: Blockvergleich — zwei Blöcke nebeneinander mit Load-Summe, Zonenverteilung, EF-Median

---

## Paket J — Leistungsdiagnostik & Zonenversionierung

Kern: **nicht ein Satz Zonen, sondern eine versionierte Historie pro Modalität.**

Begründung: Der LTHR wurde im April von einer Formelschätzung auf den race-derived Wert 168 korrigiert. Alle Sessions davor sind gegen die alten Zonen klassifiziert. Ohne Versionierung ist jede Langzeit-Zonenanalyse still falsch.

### J1 — Schema

```sql
create table if not exists diagnostics (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  performed_on date not null,
  modality text not null,          -- 'run' | 'bike' | 'strength' | 'capacity'
  protocol text not null,          -- 'ramp' | 'ttp20' | 'race' | 'field_lthr' | 'hrmax' | 'manual'
  results jsonb not null,          -- {lthr, hrmax, ftp, vdot, pace_threshold, ...}
  confidence text check (confidence in ('high','medium','low')),
  notes text,
  created_at timestamptz default now()
);

create table if not exists zone_sets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  diagnostic_id uuid references diagnostics(id) on delete set null,
  modality text not null,
  valid_from date not null,
  valid_to date,                   -- null = aktuell gültig
  zones jsonb not null,            -- [{n:1,label:'Regeneration',hr_lo:null,hr_hi:124,recoveryFactor:0.5}, ...]
  derivation text,                 -- angewandte Formel/Regel, nachvollziehbar
  created_at timestamptz default now()
);
create index if not exists zone_sets_lookup_idx on zone_sets (user_id, modality, valid_from);
```

### J2 — Bestandsdaten migrieren

Aktuelle Zonen aus `localStorage` als initiales `zone_sets`-Paar anlegen:

- Modalität `run`: Z1 <125 · Z2 125–140 · Z3 141–155 · Z4 156–168 · Z5 >168, Basis LTHR 168 / HFmax 192
- Modalität `bike`: Z1 <115 · Z2 115–130 · Z3 131–145 · Z4 146–158 · Z5 >158, Basis FTP ~200–210 W
- `valid_from` = Datum der April-Kalibrierung, `derivation` = `'LTHR-basiert, race-derived (10 km 46:14)'`
- `localStorage` bleibt Lesecache; Quelle der Wahrheit ist ab jetzt `zone_sets`

### J3 — Erfassungsablauf

1. Diagnostik anlegen → Modalität + Protokoll wählen
2. Rohwerte eingeben (protokollabhängige Felder: Ramp → max. Stufenleistung; TT20 → Ø-Watt; Race → Distanz/Zeit/Ø-HF)
3. App berechnet Zonenvorschlag und zeigt die angewandte Regel im Klartext
4. **Manuelle Korrektur jedes Zonenwerts möglich** — verpflichtend, weil Ramp-Ergebnisse bei starkem anaeroben Anteil zu hoch ausfallen; Korrektur wird in `derivation` protokolliert
5. Speichern: neues `zone_sets` mit `valid_from` = heute; vorheriges Set bekommt `valid_to` = heute − 1 Tag

Die Modalitätsverschiebung Rad/Lauf (~10–12 bpm) ergibt sich aus zwei getrennten Diagnostiken und wird nicht mehr als Sonderfall behandelt.

### J4 — Zonenauflösung bei der Klassifikation

Zentrale Funktion:

```js
// resolveZoneSet(modality, date) -> zone_set gültig an diesem Datum
```

Alle Zonenklassifikationen laufen darüber. Zusätzlich eine App-Einstellung mit zwei Modi:

- **historisch korrekt** (Default): jede Session wird gegen das zu ihrem Datum gültige Set klassifiziert. Im Chart wird an jedem `valid_from` eine vertikale Markierung gezeichnet.
- **retrospektiv normalisiert**: alle Sessions gegen das aktuelle Set. Chart-Untertitel weist den Modus explizit aus.

Der Modus wird nie still gewechselt.

### J5 — Diagnostik-Zeitreihe als Chart

Eigenes Chart in der Auswertung: LTHR, HFmax, FTP, VDOT als Punkte über Monate, je Modalität eine Serie, Punktgröße nach `confidence`.

Das ist die einzige Kurve der App, die **Leistungsentwicklung** statt Trainingsumfang zeigt.

---

## Querschnittliche Anforderungen

- Alle neuen Emojis/Icons als HTML-Entities (GitHub-Pages-UTF-8)
- Theming ausschließlich über CSS-Variablen, keine strukturellen HTML-Änderungen für Farbwechsel
- Alle DB-Inserts mit Fallback ohne neue Spalten, falls Migration nicht gelaufen ist; Constraint-Fehler lesbar durchreichen
- Nach jeder Etappe: Syntaxprüfung und Kontrolle auf ausgeglichene `div`-Struktur (bekannte Whitescreen-Ursache)
- Touch-Ziele ≥ 44 px, Long-Press-Schwelle 400 ms, alle Drag-Interaktionen mit Undo-Toast
- Neue Berechnungen ohne Netzwerkzugriff, damit die PWA offline nutzbar bleibt

## Etappenschnitt für Claude Code

| Etappe | Inhalt | Prüfkriterium |
|---|---|---|
| 1 | N1–N4 | Kennzahlen vor/nach identisch außer ACWR; ACWR plausibel gegen Handrechnung |
| 2 | A1–A4 | Ghost anlegen, verschieben, löschen; Auswertungen unverändert |
| 3 | A5–A8 | Live-Band korrekt; Import koppelt statt zu überschreiben |
| 4 | B1–B4 | Swipe auf iOS Safari flüssig, Dots korrekt, Charts lazy |
| 5 | F1–F5 | Block über Quartal anlegen, erscheint im Monat, Filter greift |
| 6 | J1–J5 | Alte Sessions gegen altes Set klassifiziert, Bruchmarkierung sichtbar |
