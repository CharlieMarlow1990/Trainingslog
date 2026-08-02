# Paket G — Blockvorlagen, Makrobilanz, Eintritts-/Austrittslogik

**Baut auf Paket F/F2 auf.** Blöcke, Zeitspannen, Wochenzeit- und Verteilungsziele existieren bereits. Paket G ergänzt: eine Vorlagenbibliothek, Dosisbänder (min/opt/ceil), Erhaltungsreize als Untergrenzen, und eine rollende Makrobilanz, gegen die Blöcke freigegeben und verrechnet werden.

**Leitgedanke:** Polarisierung ist eine Makrogröße. Ein einzelner Block darf in sich das Gegenteil von 80/20 sein — bewertet wird das rollende 84-Tage-Fenster. Blöcke setzen Reizspitzen auf ein LIT-Fundament, sie ersetzen es nicht.

**Nicht im Scope:** Scheduler/Kalenderzuordnung, Schicht- oder Verfügbarkeitsmodell, Experiment-/A-B-Framework, KI-Trainingsvorschläge.

---

## 1 · Was bereits vorhanden ist

Vor dem Bauen prüfen — vieles ist da und wird wiederverwendet, nicht ersetzt:

| Vorhanden | Datei/Funktion | Rolle in Paket G |
|---|---|---|
| Blöcke als Zeitspannen | `blocks`-Tabelle, `DB.getBlocks/addBlock/updateBlock` | unverändert |
| Intentionen | `BLOCK_INTENTIONS`, `BLOCK_INTENTION_COLORS` | um `Kraft` erweitert |
| Block-Editor | `openBlockModal`, `saveBlockFromModal` | neue Sektion oberhalb „Ziel" |
| Ziel-Zeilen pct + count | `blockGoalRowHTML`, `collectGoalMap` | Basis für Dosisbänder |
| Weiche Warnung | `updateBlockGoalWarnings` | Muster für Eintrittsbedingungen |
| Ist-Berechnung | `computeBudgetActuals(startD,endD)` | **wird die Makrobilanz** |
| Session-Goal-Zonenlogik | in `computeBudgetActuals` | unverändert übernehmen |
| Kraft-Ausschluss | `isSportZoneBased` | unverändert übernehmen |
| Budget-Panel | `renderBudgetPanel`, `renderLogBudgetSlotForBlock` | um Floor-Zeile ergänzt |
| Info-Popover | `openBlockInfoPopover` | um Vorlagen-Kopfzeile ergänzt |

### 1.1 Die Rate-Invariante existiert bereits

`weekly_target_min` und `zone_targets[k].count` sind Wochenraten, `starts_on`/`ends_on` ist der Container. Eine Blockverlängerung ist damit automatisch ratenerhaltend — kein `preserve: rate|dose`-Mechanismus nötig.

**Was fehlt:** die Sichtbarkeit des Dichteverlusts bei count-basierten Zielen. Wird ein Block von 7 auf 10 Tage gezogen, bleiben 2 HIT-Einheiten pro Woche nominal 2 — real absolviert werden aber 2 auf 10 Tage, also 1.4/7d. Siehe §5.

### 1.2 Die Makrobilanz ist ein Funktionsaufruf

```js
// 84-Tage-Fenster, Wochenäquivalent, Session-Goal-Methode,
// zoneBased-Filter — alles bereits in computeBudgetActuals.
function computeMacroBalance(today=new Date()){
  const start=new Date(today); start.setDate(start.getDate()-83);
  const a=computeBudgetActuals(start,today);
  const zt=a.zoneTotalMin||1;
  return {
    tid:{ LIT:a.zoneMin.LIT/zt, MIT:a.zoneMin.MIT/zt, HIT:a.zoneMin.HIT/zt },
    zoneTotalMin:a.zoneTotalMin,
    weeklyMin:a.totalMin,
    sportMin:a.sportMin,
    runKm:computeRunKm7d(),          // neu, §4.2
    daysSince:computeDaysSince(),    // neu, §4.3
    litDebt:computeLitDebt(),        // neu, §6.2
    acwr:currentAcwr()               // vorhandene ACWR-Berechnung
  };
}
```

**Vorbedingung:** Die ACWR-Berechnung muss auf echte rollende 7/28-Tage-Fenster umgestellt sein (bekannte Limitierung: aktuell Kalenderwochen-Buckets). Sobald Blöcke ≠ 7-Tage-Vielfache üblich werden, verschiebt sich die Kalenderwochen-Zuordnung gegen die Blockgrenzen. Entweder vorziehen oder in Paket G mitziehen.

---

## 2 · Migration

```sql
-- docs/migrations/2026-08-XX-paket-g.sql
alter table blocks
  add column template_id      text,
  add column template_version int,
  add column dose_bands       jsonb,   -- {key:{min,opt,ceil,lock}}
  add column floors           jsonb,   -- [{key,op,value,unit,lock}]
  add column modified         boolean default false,
  add column modified_fields  text[],
  add column exit_booking     jsonb;   -- beim Abschluss gebucht
```

Alle Spalten nullable. Bestehende Blöcke ohne `template_id` verhalten sich exakt wie bisher — Paket G ist rein additiv.

`A1_COLS`-Analogie beachten: Falls es eine Spaltenliste für `blocks` gibt, dort ergänzen.

---

## 3 · Vorlagenbibliothek

**Als JS-Konstante in `index.html`**, analog `BLOCK_INTENTIONS` — nicht als Supabase-Tabelle. Statisch, versioniert, kein Sync nötig.

```js
const BLOCK_TEMPLATES=[ /* … */ ];
const BLOCK_TEMPLATE_VERSION=1;
```

### 3.1 Objektform

```jsonc
{
  "id": "hit_block_run",
  "name": "HIT-Block Lauf",
  "intention": "HIT",                    // aus BLOCK_INTENTIONS
  "source": { "authors":"Nuuttila et al.", "year":2017,
              "journal":"Int J Sports Med 38:909–920",
              "population":"32 freizeittrainierte Männer, 19–37 J" },
  "evidence": "RCT",                     // RCT|kontrolliert|einzelfall|deskriptiv
  "days": { "nominal":7, "min":7, "max":7, "rigid":true },
  "recoveryDays": [5,7],
  "doseBands": {
    "weekly_target_min": { "min":240, "opt":330, "ceil":420, "lock":"free" },
    "zone.HIT.count":    { "min":3,   "opt":4,   "ceil":5,   "lock":"fixed" },
    "sport.lauf.count":  { "min":1,   "opt":2,   "ceil":2,   "lock":"fixed" }
  },
  "zoneTargetsDefault": { "LIT":{"pct":45}, "MIT":{"pct":5}, "HIT":{"pct":50} },
  "floors": [
    { "key":"run_km",         "op":">=", "value":12, "unit":"km_per_7d",       "lock":"bounded" },
    { "key":"zone.LIT.count", "op":">=", "value":1,  "unit":"sessions_per_7d", "lock":"bounded" },
    { "key":"strength_heavy", "op":">=", "value":1,  "unit":"sessions_per_10d","lock":"bounded" }
  ],
  "entry": [
    { "key":"tid.LIT",        "op":">=", "value":0.80, "label":"LIT-Anteil 84 d" },
    { "key":"runKm",          "op":">=", "value":15,   "label":"Lauf-Basis" },
    { "key":"daysSince.HIT",  "op":">=", "value":28,   "label":"letzter HIT-Block" },
    { "key":"acwr",           "op":"<=", "value":1.25, "label":"ACWR" }
  ],
  "exit": { "litDebtWeeks":2.5, "lockDays":28 },
  "protocols": ["run_4x4","run_3x10x30_15","run_6x3","run_10_20_30",
                "bike_ronnestad_30_15","capacity_generic"],
  "noteDe": "…"
}
```

**Dosisband-Keys** adressieren bestehende Felder per Pfad:
- `weekly_target_min` → Spalte
- `zone.<LIT|MIT|HIT>.<pct|count>` → `zone_targets`
- `sport.<key>.<pct|count>` → `sport_targets`

Damit schreibt die Vorlage in das vorhandene Zielmodell, statt ein zweites aufzumachen.

**Lock-Level:** `fixed` (Änderung → `modified=true` + Feldname in `modified_fields`), `bounded` (außerhalb min/ceil → Warnung + Flag), `free`.

### 3.2 Startvorlagen

#### G1 · LIT-Akkumulation
```
intention   LIT     evidenz  deskriptiv (Seiler TID / Rønnestad & Hansen 2017)
days        21 · 14–28 · elastisch
doseBands   weekly_target_min   240 / 360 / 480   free
            zone.LIT.pct         80 /  88 /  95   bounded
            run_km               12 /  18 /  22   bounded
floors      zone.HIT.count ≥ 1/7d · strength_heavy ≥ 1/10d
entry       —  (Basisvorlage, immer wählbar)
exit        litDebtWeeks −1 je 7 Tage (Guthaben) · lockDays 0
```

#### G2 · HIT-Block Lauf
```
intention   HIT     evidenz  RCT
quelle      Nuuttila et al. 2017 · 32 freizeittrainierte Männer, 19–37 J
days        7 · rigid       recovery 5–7 d
doseBands   zone.HIT.count       3 / 4 / 5    fixed
            sport.lauf.count     1 / 2 / 2    fixed
            weekly_target_min  240 / 330 / 420  free
floors      run_km ≥ 12/7d · zone.LIT.count ≥ 1/7d · strength_heavy ≥ 1/10d
entry       tid.LIT ≥ .80 · runKm ≥ 15 · daysSince.HIT ≥ 28 · acwr ≤ 1.25
exit        litDebtWeeks 2.5 · lockDays 28

noteDe  Studie: 4–5 HIT je Woche in Blockwochen, Erholungswochen mit einer.
        Alternative Modalitäten für LIT ausdrücklich erlaubt (Überlastungsschutz).
        Beobachtet: maximale Laufgeschwindigkeit sank in den ersten vier Wochen —
        Kraft-Floor während des Blocks nicht streichen.
        Ceiling bewusst 5 statt 6: Comeback-Anpassung.
```

#### G3 · MIT-Impact
```
intention   MIT     evidenz  RCT
quelle      Mølmen et al. 2025 · gut trainierte Radfahrer
days        7 · rigid       recovery 6 d
doseBands   zone.MIT.count       5 / 6 / 6    fixed
            weekly_target_min  300 / 420 / 540  bounded
floors      run_km ≥ 12/7d · strength_heavy ≥ 1/10d
entry       tid.LIT ≥ .80 · weeklyMin ≥ 300 · daysSince.MIT ≥ 28 · acwr ≤ 1.20
exit        litDebtWeeks 2.0 · lockDays 28

noteDe  Die Dichte ist die Intervention: sechs Einheiten in sieben Tagen.
        Auf zehn Tage gedehnt entsteht ein anderer, schwächerer Block — rigid.
        Unter 5 h/Woche nicht sinnvoll: die Einzeldosis würde unterschritten.
```

#### G4 · 10-20-30
```
intention   HIT     evidenz  kontrolliert
quelle      Gunnarsson & Bangsbo 2012 · 18 mäßig trainierte Läufer, VO₂max ~52
days        28 · 21–49 · elastisch
doseBands   zone.HIT.count       2 / 3 / 3    fixed
            weekly_target_min  150 / 210 / 300  free
floors      strength_heavy ≥ 1/10d · zone.LIT.count ≥ 1/7d
entry       runKm ≥ 12 · acwr ≤ 1.30
exit        litDebtWeeks 0.5 je 7 Tage · lockDays 0

noteDe  30 s locker / 20 s Dauerlauftempo / 10 s Sprint, fortlaufend über 5 min,
        2 min Pause, 3–4 Blöcke.
        Studienbelastung: mittlere HF ~85 %, Spitze ~96 % HFmax
        (aus cfg-Zonen einsetzen). Ergebnis: VO₂max +4 % bei 54 % weniger Umfang.
        COMEBACK: erste 3–4 Wochen den 10-s-Anteil zügig statt als Sprint laufen.
        Als Notfallvorlage geeignet, wenn eine Woche auf 4 h schrumpft.
```

#### G5 · Kraftaufbau
```
intention   Kraft   evidenz  —  (keine Studienvorlage, bewusst offen)
days        21 · 21–42 · elastisch
doseBands   sport.kraft.count    1 / 3 / 4    free      ← einzige Kerngröße
            weekly_target_min  240 / 300 / 420  free
zoneTargets —  (leer; hasAnyBlockTargets greift über sport_targets)
floors      run_km ≥ 12/7d · zone.HIT.count ≥ 1/7d · zone.LIT.min ≥ 120min/7d
            alle bounded
entry       acwr ≤ 1.25
exit        litDebtWeeks 0.5 · lockDays 0

noteDe  Kein Dosisband auf Sätzen, Last oder Übungswahl — das steuerst du selbst.
        Einstellbar ist nur die Reizdichte (Einheiten je 7 Tage).
        Die App prüft, ob die Ausdauer-Floors bei der gewählten Dichte
        ins Zeitbudget passen, und bucht den Block in die Makrobilanz.
        Achsentausch: Kraft ist Kern, Ausdauer wird Floor. Bei Zeitknappheit
        Rad kürzen, nicht Laufen — Umfangskontinuität ist im Comeback wichtiger.
```

**Wichtig zu G5:** Der Kraftblock ist absichtlich anders geartet. Bei Ausdauer trägt die Vorlage eine Studiendosis; bei Kraft trägt der Nutzer sie aus eigener Erfahrung. Keine Intentions-Untertypen, keine Satzvorgaben.

`BLOCK_INTENTIONS` um `'Kraft'` erweitern, Farbe in `BLOCK_INTENTION_COLORS` ergänzen. `zone_targets` bleibt leer — `hasAnyBlockTargets` prüft bereits `sport_targets` mit.

---

## 4 · Neue Berechnungen

### 4.1 Erhaltungsreiz-Prüfung

```js
// Prüft floors[] gegen den laufenden Block bzw. das rollende Fenster.
// Rückgabe je Floor: {key,label,required,actual,met}
function evaluateFloors(floors, block, macro){ … }
```

Fensterwahl je Floor-Unit:
- `*_per_7d` → letzte 7 Tage rollend
- `*_per_10d` → letzte 10 Tage rollend
- Innerhalb eines laufenden Blocks: Fenster auf `starts_on` klemmen, solange der Block kürzer als das Fenster ist

### 4.2 `computeRunKm7d()`

Laufdistanz der letzten 7 Tage. Setzt voraus, dass Distanz je Session vorliegt (GPX/FIT). Fehlt sie, Floor als „nicht prüfbar" ausweisen statt als verletzt — sonst warnt die App gegen fehlende Daten statt gegen fehlendes Training.

### 4.3 `computeDaysSince()`

```js
{ LIT:3, MIT:63, HIT:49, Kraft:68, strengthHeavy:11 }
```

Zwei Ebenen: Tage seit letztem **Block** dieser Intention (aus `blocks`), und Tage seit letzter **Einheit** (`strengthHeavy` aus `sessions` mit Sportart Kraft). Erstes speist Eintrittsbedingungen, zweites die Floors.

### 4.4 Realisierbarkeit

Beim Speichern im Editor, blockiert nicht:

**Abstandsprüfung** — harte Einheiten × Mindestabstand ≤ Blockdauer.
Mindestabstand konservativ 24 h; bei `zone.HIT.count` > `days/1.5` warnen.

**Volumenprüfung** — geschätzte Kernreizdauer + Floor-Dauern gegen `weekly_target_min`.
Protokolldauern aus `SESSION_PROTOCOLS[].durationMin`; ohne gewähltes Protokoll Default 50 min je harte Einheit.

```
Rest = weekly_target_min − (Kernreiz + Floors)
Rest < 0      → Volumen reicht nicht (Warnung)
Rest < 30 min → Residualvolumen aufgebraucht (Hinweis)
```

---

## 5 · Reizdichte bei Blockdehnung

Der einzige Punkt, an dem die vorhandene Rate-Semantik nicht ausreicht.

```js
// zone_targets[k].count ist nominal pro Woche. Wird der Block gedehnt,
// sinkt die real erreichbare Dichte, wenn die Gesamtzahl konstant bleibt.
function densityReadout(block,template){
  const days=blockDays(block);
  const nominal=block.zone_targets?.HIT?.count ?? null;
  if(nominal==null) return null;
  const perCycle=Math.round(nominal*days/7);
  const realRate=perCycle*7/days;
  return { perCycle, realRate, ratio:realRate/nominal };
}
```

Anzeige im Editor bei `days !== template.days.nominal`:

```
Reizdichte  2 je 10 Tage = 1.4 / 7d  ·  −30 % gegenüber Vorlage
```

Bei `template.days.rigid === true` die Dehnung im Editor gar nicht anbieten und im Kalender-Block-Modus die Kanten-Handles sperren (`.cal-block-handle` ausblenden bzw. `pointer-events:none`).

---

## 6 · Eintritt und Austritt

### 6.1 Eintritt

```js
function evaluateEntry(template, macro){
  return (template.entry||[]).map(c=>({
    key:c.key, label:c.label, required:c.value, op:c.op,
    actual:resolvePath(macro,c.key),
    met:compare(resolvePath(macro,c.key),c.op,c.value)
  }));
}
```

**Verhalten:** Nicht erfüllte Bedingungen werden angezeigt, blockieren aber nicht — dasselbe Muster wie `updateBlockGoalWarnings`. Wird trotz offener Bedingung gespeichert, landet das in `exit_booking.entryOverride`.

Bei weniger als 28 Tagen Historie: Makrobilanz zeigt „unzureichende Datenlage", Eintrittsprüfung entfällt vollständig.

### 6.2 Austritt und LIT-Rückstand

Beim Abschluss eines Blocks (Enddatum überschritten, beim nächsten Render):

```js
block.exit_booking = {
  completedAt, complianceP,          // erreichte vs. geplante Dosis
  litDebtWeeks: template.exit.litDebtWeeks * (blockDays(block)/7),
  lockUntil:    addDays(block.ends_on, template.exit.lockDays),
  entryOverride: [...]
};
```

Rückstandskonto:

```js
function computeLitDebt(){
  let debt=0;
  for(const b of blocks) if(b.exit_booking) debt+=b.exit_booking.litDebtWeeks;
  // Abbau: je abgeschlossener Woche mit LIT-Anteil > 80 %
  debt -= countWeeksAboveLit(0.80);
  return clamp(debt,0,8);
}
```

Die Abbaurate ist ein Vorschlag, keine belegte Größe — siehe §10.

---

## 7 · UI-Integration

### 7.1 Block-Editor (`openBlockModal`)

Neue Sektion **oberhalb** von „Ziel", einklappbar nach demselben Muster wie `block-goal-toggle`/`block-goal-body`:

```
Vorlage        [Select: — · LIT-Akkumulation · HIT-Block Lauf · …]
```

Bei Auswahl:
1. `intention` und Farbe setzen (bestehende Logik in `intentionEl.change` wiederverwenden)
2. Ziel-Sektion mit `zoneTargetsDefault` und `doseBands[*].opt` vorbefüllen und aufklappen
3. Dosisband-Skala unter jede betroffene Zielzeile rendern
4. Floor-Zeilen als read-only Liste
5. Eintrittsbedingungen anzeigen
6. Skalierung/Realisierbarkeit/Makroprojektion in einem Fixblock unten

**Kritisch:** `openBudgetGoalModal` teilt IDs, Klassen und Renderer mit `openBlockModal`. Die Vorlagensektion darf dort nicht gerendert werden. `blockGoalRowHTML` bekommt einen optionalen `band`-Parameter; ohne Band verhält sie sich exakt wie bisher.

```js
function blockGoalRowHTML(attr,key,label,color,target,band){
  // … bestehendes Markup unverändert …
  // + wenn band: Skala-Zeile mit min/opt/ceil und Lock-Glyph
}
```

### 7.2 Dosisband-Darstellung

Unter der Zielzeile, in der Grammatik des bestehenden Sheets (keine neuen Farben):

```
HIT                    [4] %  [4] #/Wo    🔒
├──────●──────────┤   min 3 · opt 4 · ceil 5
```

Lock-Glyphen: `🔒` fixed, `◐` bounded, kein Glyph bei free.
Werte außerhalb des Bandes: `.block-goal-warn`-Stil wiederverwenden.

### 7.3 Budget-Panel (`renderBudgetPanel`)

Fünfte Zeile ergänzen: **Erhaltungsreize**, nur wenn `block.floors` gesetzt.

```
Lauf-Umfang     13.1 / 12 km    ✓
LIT-Einheiten   1 / 1           ✓
Kraft schwer    vor 9 d · Fenster 10 d   ⚠
```

Darunter eine Zeile, die die vorhandene ACWR/Monotonie-Anzeige explizit als blockunabhängig kennzeichnet — damit bei Blöcken ≠ 7 Tage keine Verwechslung mit den Blockzielen entsteht.

### 7.4 Info-Popover (`openBlockInfoPopover`)

Kopfzeile um Vorlage und Evidenzbadge ergänzen, falls `template_id` gesetzt. Bei `modified=true` ein `(modifiziert)`-Suffix hinter dem Titel.

### 7.5 Kalender-Block-Modus

Bei `template.days.rigid`: Kanten-Handles nicht rendern. Beim Versuch, den Block zu ziehen, kurzer Toast: „Vorlage ist auf n Tage festgelegt — die Dichte ist die Intervention."

---

## 8 · Sessionprotokolle

Zweite JS-Konstante, referenziert von `template.protocols`. Zunächst reine Anzeige im Editor („erlaubte Protokolle") und als Textbaustein im Ghost-Sheet.

```js
const SESSION_PROTOCOLS={
  run_10_20_30:{ name:"10-20-30", sport:"lauf", class:"HIT",
                 structure:"3–4 × 5 min (30 s locker / 20 s DL / 10 s Sprint)",
                 durationMin:35, evidence:"kontrolliert",
                 target:c=>`Spitze ~${Math.round(c.hfmax*0.96)} bpm` },
  run_4x4:{ name:"4×4 min", sport:"lauf", class:"HIT",
            structure:"4×4 min, 3 min Pause", durationMin:45, evidence:"RCT",
            target:c=>`${Math.round(c.hfmax*0.90)}–${Math.round(c.hfmax*0.95)} bpm` },
  run_3x10x30_15:{ … }, run_6x3:{ … },
  bike_ronnestad_30_15:{ … }, bike_4x8:{ … },
  bike_5x12_mit:{ … }, run_5x10_mit:{ … },
  capacity_generic:{ … }
};
```

Zielwerte als Funktion über `cfg` (Zonen, HFmax, LTHR, FTP) — nicht als feste bpm-Werte, damit eine neue Leistungsdiagnostik alle Protokolle mitzieht.

**Substitutions- und Anrechnungsregel** (zunächst nur als Hinweistext im Editor, keine Automatik):

```
Eine Einheit belegt genau EINEN Intensitäts-Slot und HÖCHSTENS EINEN Floor.
Capacity → HIT-Slot 1.0 · VO₂max-Kernreiz 0.5 (max 1 je Block)
         → Kraft metabolisch 0.5 · Kraft schwer 0.0
```

---

## 9 · Akzeptanzkriterien

**Additivität**
- [ ] Blöcke ohne `template_id` verhalten sich unverändert
- [ ] `openBudgetGoalModal` rendert keine Vorlagensektion und funktioniert wie bisher
- [ ] `blockGoalRowHTML` ohne `band`-Parameter erzeugt identisches Markup

**Vorlagen**
- [ ] 5 Seed-Vorlagen (G1–G5), 9 Sessionprotokolle
- [ ] `BLOCK_INTENTIONS` um `Kraft` erweitert, Farbe vorhanden
- [ ] Vorlagenwahl befüllt `zone_targets`/`sport_targets`/`weekly_target_min` mit opt-Werten
- [ ] Laufende Blöcke behalten ihre `template_version`

**Lock-Level**
- [ ] Änderung an `fixed` setzt `modified=true` und trägt den Pfad in `modified_fields`
- [ ] Wert außerhalb `bounded`-Band erzeugt Warnung im `.block-goal-warn`-Stil
- [ ] `rigid`-Vorlagen: keine Kanten-Handles im Kalender, kein Dauer-Stepper im Editor

**Makrobilanz**
- [ ] `computeMacroBalance` nutzt `computeBudgetActuals` mit 84-Tage-Fenster
- [ ] Session-Goal-Zonenlogik und `isSportZoneBased`-Filter unverändert übernommen
- [ ] Kraft fließt nicht in die TID-Berechnung ein
- [ ] Bei < 28 Tagen Historie: „unzureichende Datenlage", keine Eintrittsprüfung
- [ ] ACWR-Wert stammt aus echten rollenden Fenstern, nicht aus Kalenderwochen

**Reizdichte**
- [ ] Bei `days !== nominal` erscheint der Dichtewert als Rate/7d mit Prozentabweichung
- [ ] Rate-Anzeige rechnet gegen `template.doseBands[*].opt`, nicht gegen den gespeicherten Wert

**Floors**
- [ ] Fensterlänge folgt der Unit (`_per_7d` / `_per_10d`)
- [ ] Innerhalb eines jungen Blocks wird das Fenster auf `starts_on` geklemmt
- [ ] Fehlende Distanzdaten → „nicht prüfbar", nicht „verletzt"

**Eintritt/Austritt**
- [ ] Offene Bedingungen werden angezeigt, blockieren das Speichern nicht
- [ ] Override wird in `exit_booking.entryOverride` dokumentiert
- [ ] `exit_booking` wird beim ersten Render nach `ends_on` automatisch geschrieben
- [ ] `litDebt` akkumuliert über Blöcke und wird durch LIT-lastige Wochen abgebaut

**Realisierbarkeit**
- [ ] Abstands- und Volumenprüfung laufen beim Öffnen und bei jeder Änderung
- [ ] Konflikte werden angezeigt, nicht stillschweigend aufgelöst

**Comeback-Constraints (global, vorlagenübergreifend)**
- [ ] Lauf-Umfangs-Floor ≥ 12 km/7d in jeder Ausdauervorlage
- [ ] Lauf-Progression > +10 %/Woche erzeugt eine Warnung, unabhängig von der Vorlage

---

## 10 · Entscheidungen (Stand 2026-08-02, bei der Umsetzung geklärt)

1. **Rolling-ACWR — ✅ war bereits erledigt.** `computeAcwrRollingSeries` rechnet seit Paket N2
   mit echten rollenden 7-/28-Tage-Fenstern samt `CHRONIC_MIN_HISTORY_DAYS`-Gate; die
   Kalenderwochen-Buckets sind längst weg. Kein Vorarbeit-Paket nötig, `computeMacroBalance`
   zieht den ACWR über `computeAcwrView()`.
2. **`litDebt`-Abbaurate — Formel aus §6.2 umgesetzt**, inklusive der negativen Buchung der
   LIT-Vorlage (Guthaben). `countWeeksAboveLit` zählt abgeschlossene Wochen ab dem ältesten
   `exit_booking`, gedeckelt auf 26 Wochen. Bleibt ein Vorschlag, keine belegte Größe.
3. **`run_km`-Datenquelle — Distanz, wie vorgesehen.** `sessions.distance_km` wird von
   GPX/FIT und dem Garmin-Sync befüllt. Fehlt sie bei einer Lauf-Einheit im Fenster, weist
   `evaluateFloors` den Floor als „nicht prüfbar" aus statt als verletzt.
4. **Kraft in `BLOCK_INTENTIONS` — flach ergänzt.** Farbe `#4F3796` (`--zone-5`), tiefe Stufe
   der Lila-Familie, damit sie von HIT (`--zone-4`) unterscheidbar bleibt.
5. **Protokoll-Mindest-n — entfällt in Paket G.** §8 sieht Protokolle nur als Anzeige vor;
   ohne Protokollverlauf gibt es keine Schwelle zu setzen.
6. **Pacing-Klassifikation — nicht in Paket G.** Braucht Intervall-Segmentierung aus der
   HF-/Power-Zeitreihe und ist damit ein eigenständiges Thema. Eigenes Paket.
7. **`strength_heavy` — neue Spalte `sessions.strength_type`** (`max` | `hyp` | `ausdauer`,
   Migration `2026-08-02-paket-g.sql`), Chip-Auswahl im Session-Editor bei Sport = Kraft.
   Den Floor erfüllt **nur `max`** (Maximalkraft): er schützt den neuromuskulären Reiz.
   Metabolische Belastung führt die App als eigene Sportart `Capacity`, nicht als Kraft-Typ.
   Einheiten ohne gepflegten Typ ergeben „nicht prüfbar", nicht „verletzt".

### 10.1 Abweichungen der Umsetzung von der Spec

- **Sport-Keys großgeschrieben.** Die Spec notiert `sport.lauf.count`; die realen
  `cfg.sports[].key` sind `Rad`, `Lauf`, `Kraft`, `Capacity`. Die Vorlagen nutzen die echten
  Keys, `resolveSportKey` löst zusätzlich case-insensitiv auf.
- **Protokoll-Zielwerte über %HFmax / %FTP.** Die App führt kein LTHR — `cfg.hrMax` und
  `cfg.ftp` sind die verfügbaren Bezugsgrößen.
- **`run_km`-Floor auch in G1 und G4.** §3.2 listet ihn dort nicht, §9 fordert ihn aber für
  *jede* Ausdauervorlage. Das Akzeptanzkriterium gewinnt.
- **Volumenprüfung nimmt das Maximum der Ausdauer-Floors, nicht ihre Summe.** Ein lockerer
  Lauf erfüllt `run_km` und `zone.LIT.count` gleichzeitig; addiert warnte die App schon bei
  den opt-Werten einer studienbelegten Vorlage gegen sich selbst.
- **Floors in einem jungen Block sind „läuft noch", nicht verletzt.** §4.1 klemmt das Fenster
  auf `starts_on`; ohne diesen Zusatz wäre am ersten Blocktag jeder Wochen-Floor rot.
- **Kein Dauer-Stepper für `rigid` nötig** — der Editor hat keinen. Stattdessen schnappt die
  Vorlagenwahl `ends_on` auf die Nominaldauer, und im Kalender entfallen die Kanten-Handles.

---

## 11 · Quellenlage

| Vorlage | Quelle | Population | Übertragbarkeit |
|---|---|---|---|
| G1 LIT | Seiler TID-Review; Rønnestad & Hansen 2017 | elitär / Einzelfall | Prinzip ja, Volumen nein |
| G2 HIT Lauf | Nuuttila et al. 2017 | 32 freizeittrainierte Männer 19–37 | **hoch** |
| G3 MIT-Impact | Mølmen et al. 2025 | gut trainierte Radfahrer | mittel, Radmodalität |
| G4 10-20-30 | Gunnarsson & Bangsbo 2012 | 18 mäßig trainierte Läufer, VO₂max ~52 | **hoch** |
| G5 Kraft | — | — | bewusst offen |

**Einordnung, die in der Bibliothek sichtbar sein sollte:** Über 12 Wochen fand sich bei trainierten Radfahrern kein Unterschied zwischen blockperiodisiertem und gut gemachtem traditionellem Training. Blockvorlagen sind Strukturhilfen mit belegten Dosierungen — kein nachgewiesen überlegenes Modell. Der Nutzen liegt im Reizwechsel und in der Planbarkeit.
