# Handoff: Monats-Zoom in Wochentagsansicht mit Tages-ACWR

## Kontext
Ablösung des bisherigen Plans, ACWR direkt in der Monatsansicht (Zweitachse/Whisker) zu zeigen. Stattdessen: Monatsansicht bleibt reine Wochenlast-Bubble-Chart wie heute. ACWR erscheint ausschließlich in einer neuen Drilldown-Ansicht, die durch Antippen einer Wochen-Bubble geöffnet wird.

## Scope

1. **Monatsansicht:** unverändert (Wochenlast-Bubbles, Kalenderwoche). Kein ACWR, keine Whisker, keine Zweitachse.
2. **Tap auf Wochen-Bubble:** Zoom-Transition öffnet Tagesansicht dieser Woche.
3. **Tagesansicht:** gewählte Woche (7 Tage) hervorgehoben + je **7 Kontexttage davor und danach** (21 Tage Datenbereich insgesamt).
4. **ACWR (echtes tägliches Rolling 7/28-Fenster)** nur hier, als Linie mit Sweet-Spot-Band 0,8–1,3 auf rechter Achse, durchgängig über den gesamten 21-Tage-Bereich.
5. **Horizontales Scrollen/Pannen** innerhalb der Tagesansicht, da 21 Tage nicht auf einen Screen passen.
6. **Zurück** (Button/Geste) → Reverse-Zoom in die Monatsansicht.

## Datenbasis

- Baut auf der ohnehin geplanten Konsolidierung `buildDailyLoadSeries()` auf — diese Tagesreihe ist die einzige Quelle für Wochensummen (Monatsansicht) **und** Tageswerte/ACWR (Zoomansicht). Keine zwei parallelen Berechnungswege.
- ACWR pro Tag *t*:
  - `acute7 = Summe(load, t-6…t)`
  - `chronic28 = Durchschnitt(load, t-27…t) * 7` (Wochenäquivalent)
  - `ratio = acute7 / chronic28`
- **Harte Voraussetzung:** ACWR nur berechnen/zeigen, wenn ≥28 Tage Historie vor *t* existieren. Kein Näherungswert mit verkürztem Fenster. Fehlt die Historie (z. B. Saisonbeginn), bleibt Linie/Achse für diesen Teilbereich einfach leer statt eines verzerrten Frühwerts.

## Zoom-Interaktion (Monat → Woche)

- **FLIP-Technik**, kein Fade/Cut. Start-Zustand = exakte Bildschirmposition **und** Radius der getappten Bubble als `transform-origin` + initiale Skalierung — die Bubble selbst wird zum Fenster, durch das reingezoomt wird (nicht nur ein Punkt-Origin mit beliebigem Startscale).
- Zielskalierung/Position berechnet aus Bubble-Geometrie, nicht aus fixem Wert (z. B. nicht pauschal `scale(0.04)`).
- Timing: ca. 400–500 ms, ease-out (schnell rein, sanft andocken). Monatsansicht parallel leicht hochskalieren + ausblenden, kein harter Schnitt.
- Rückweg exakt spiegelbildlich: gleicher Origin, reverse Easing.

## Tagesansicht — Layout

- **Ausgewählte Woche:** visuell hervorgehoben (dunkler/größer, leicht hinterlegter Bereich als Blockmarkierung).
- **Kontexttage** (7 davor, 7 danach): gedimmt/kleiner (grau), klar als Kontext erkennbar, nicht gleichwertig zur Auswahl.
- **Scroll-Startposition:** zentriert auf die ausgewählte Woche, nicht am linken Rand des 21-Tage-Bereichs.
- **ACWR-Linie + Sweet-Spot-Band** laufen durchgängig über den gesamten scrollbaren Bereich (rechte Achse), nicht nur über die Auswahlwoche.
- Scroll-Mechanik: natives horizontales Touch-Scroll/Pan. Kein Zwang zum Einrasten auf Tagesraster, optional als Verfeinerung späterer Iteration.

## Randfälle

- **Anfang der Trainingshistorie** (erste Wochen): weniger als 7 Kontexttage verfügbar → nur so viele zeigen wie vorhanden, keine Platzhalter-/Faketage.
- **Aktuelle, unvollständige Woche:** ausgewählte Woche hat ggf. < 7 reale Tage → keine leeren Bubbles für die Zukunft, ACWR-Linie endet am letzten tatsächlichen Tag.
- **ACWR-freie Frühphase** (< 28 Tage Gesamthistorie): Achse/Linie erscheint erst ab dem Tag, an dem die Voraussetzung erfüllt ist; davor nur Tagesbubbles ohne ACWR-Overlay.

## Offene Entscheidung

- Soll die horizontale Scrollposition beim Schließen/Wiederöffnen der Zoomansicht persistieren, oder startet sie bei jedem Öffnen neu zentriert auf die gewählte Woche?
