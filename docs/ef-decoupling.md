# Feature: Aerobe Effizienz (EF + Decoupling)

## Kontext
Erweiterung der Trainingslog-App um eine Effizienz-Analyse, die aus HF, Pace/Power und Dauer
Rückschlüsse auf aerobe Fitness-Trends ableitet. Ergänzt die bestehende Workload-Progression-
und Zonen-Analyse um ein sport-spezifisches Effizienzsignal.

Referenzimplementierung (Optik/Interaktion, bereits mit Nutzer abgestimmt):
`/mnt/user-data/outputs/ef-preview.html` (Standalone-Datei mit Dummy-Daten) — Struktur, Farben,
Tooltip-Verhalten und Band-Logik von dort übernehmen, aber an das bestehende Theming
(CSS-Variablen, kein Strukturumbau) und an echte `DB.getSessions()`-Daten anpassen.

## Betroffene Datei
`index.html` (Single-File-App)

## 1. Sample-Level-Vorverarbeitung (neue Funktion)

Ort: gleiche Ebene wie bestehende Analyse-Funktionen (z.B. neben `computeMonotonyStrain()`).

Neue Funktion `computeEfficiency(session)`:
- Input: eine Session mit Sample-Zeitreihe (HF + Pace/Power über Zeit), wie sie aus
  GPX/TCX/FIT-Import bereits vorliegt
- Analysefenster = Bewegungszeit MINUS:
  - erste 300s (HF-Anlauf/Kinetik-Stabilisierung)
  - Pausen/Stops (Rad: auch Rollphasen mit Power = 0)
- EF = mean(power|speed, Analysefenster) / mean(HR, Analysefenster)
  - Rad: EF = avgPower(Fenster) / avgHR(Fenster)
  - Lauf: EF = (Distanz/Zeit in m/min, Fenster) / avgHR(Fenster)
- Decoupling = Vergleich 1. vs. 2. Hälfte DES ANALYSEFENSTERS (nicht der Gesamtdauer):
  `(EF_Hälfte1 - EF_Hälfte2) / EF_Hälfte1 * 100`
- WICHTIG: EF und Decoupling müssen auf demselben Zeitfenster (nach 300s-Abzug) beruhen,
  damit beide Werte aus derselben Grundgesamtheit stammen

Rückgabe: `{ ef, decoupling, analysisWindowSec }` oder `null`, wenn Session nicht qualifiziert.

## 2. Qualifikationsfilter (neue Funktion)

Neue Funktion `qualifiesForEF(session)`:
- Sport-Modalität eindeutig (Rad/Lauf getrennt, nie gemischt)
- Analysefenster (nach 300s-Abzug) ≥ 40 min → Gesamtdauer muss ≥ ca. 45 min sein
- ≥ 80% der Zeit in Z1/Z2 (Config-Zonen aus `cfg.sportZones` nutzen, nicht hartkodieren)
- Keine Intervallstruktur / kein signifikanter Z4+-Anteil

Sessions, die diesen Filter nicht bestehen, fließen NICHT in die EF-Serie ein, erscheinen aber
als graue Ticks auf der Zeitachse (siehe Referenzdatei: `runExcluded`/`bikeExcluded`-Pattern).

## 3. Persistenz

Bei Session-Insert/Update: `ef`, `decoupling`, `analysisWindowSec` als abgeleitete Felder
berechnen und mitspeichern (spart Neuberechnung bei jedem Chart-Render).

- Neue Supabase-Spalten auf der Sessions-Tabelle: `ef numeric`, `decoupling numeric`,
  `analysis_window_sec integer` (alle nullable)
- SQL-Migration mit Fallback-Logik nach bestehendem Muster: Insert darf nicht scheitern,
  wenn Migration noch nicht gelaufen ist; Spalten in dem Fall einfach weglassen und
  lesbaren Fehler nur bei echten Constraint-Verletzungen zeigen

## 4. Trend-Aggregation (neue Funktion)

Neue Funktion `computeEfTrend(sport)`:
- Rolling Median über die letzten 5 qualifizierten Sessions (± MAD-Band)
- Baseline (Median der ersten Hälfte der letzten ~8 Wochen qualifizierter Sessions)
  vs. aktuell (Median der letzten 3 qualifizierten Sessions)
- Verdict-Logik (siehe Referenzdatei `verdict()`):
  - EF-Anstieg ≥3% + Decoupling stabil/sinkend → "Fitness steigt"
  - EF-Anstieg ≥3% + Decoupling steigend → "prüfen" (Warnung, kein reines Positiv-Signal)
  - EF-Abfall ≥3% → "Kontext prüfen" (nie automatisch als Formverlust werten)
  - < 6 qualifizierte Sessions → "Baseline im Aufbau", kein Band rendern

## 5. Darstellung (neue Chart-Funktion, SVG wie bestehende Charts)

Zwei Karten, analog zur bestehenden Workload-Progression-Karte:
- Karte 1: Laufen, Karte 2: Rad (getrennt, da EF-Skalen nicht modalitätsübergreifend
  vergleichbar sind — bestehender 10-12bpm-Offset gilt sinngemäß auch hier)
- Pro Karte: EF als Punkte (Größe ~ Dauer) + Rolling-Median-Band auf linker Y-Achse;
  Decoupling als dünne Linie/Kreise auf rechter Y-Achse, INVERTIERT (0% oben, damit
  "gut" bei beiden Serien optisch nach oben zeigt)
- Referenzlinien bei 5%/10% Decoupling
- Graue Ticks für nicht-qualifizierte Sessions (Intervalle, <40min Analysefenster)
- Tooltip bei Hover/Tap: Datum, Dauer, avgHR, avgPace/Power, EF, Decoupling
- Verdict-Text über jeder Karte (aus `computeEfTrend()`)
- Bei <6 qualifizierten Sessions: Punkte zeichnen, Band unterdrücken, "Baseline im
  Aufbau" anzeigen statt einer Trendaussage

Styling: bestehende CSS-Variablen des Theming-Systems verwenden (keine neuen
Hardcoded-Farben außerhalb der Variablendefinition), Emojis falls verwendet als
HTML-Entities.

## 6. Platzierung im UI

Gleiche Grid-Sektion wie Workload-Progression-Chart, direkt darunter oder daneben
(mit Nutzer noch final abzustimmen). Gleiches X-Achsen-Zeitfenster wie die
Workload-Progression, damit beide Charts übereinander lesbar sind.

## Offene Punkte, die vor Umsetzung noch zu klären sind
- Exakte Platzierung im Layout (unter/neben Workload-Progression?)
- Ob `analysisWindowSec` auch für andere bestehende Metriken rückwirkend genutzt
  werden soll oder nur für dieses Feature
- Verhalten bei Sample-Daten mit Lücken (GPS-Dropout, Pausenerkennung bereits
  vorhanden aus GPX-Parser? prüfen vor Neuimplementierung)

## Nicht in Scope für diesen Prompt
- HR-Recovery-Metrik (separates Feature, später)
- Rückwirkende Neuberechnung historischer Sessions (separat klären: Batch-Job nötig?)
