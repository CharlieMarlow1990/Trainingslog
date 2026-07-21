# Trainingslog — Design-Überarbeitung

**Repo/Live:** https://charliemarlow1990.github.io/Trainingslog/
**Kontext:** Fitness-Tracking-PWA. Screens: Log, Kalender, Auswertung, Bibliothek, KI, Mehr.

## Auftrag in einem Satz

Die App bekommt eine Y2K/Grunge/Poster-Ästhetik (Referenzen unten), ohne dass die
funktionale Dichte der App (GPX-Import, Zonen-Editor, TRIMP/TSS, KI-Analyse,
Workload-Progression) darunter leidet. Ästhetik hat Priorität — aber über eine
**feste Grammatik**, nicht über acht verschiedene Stile nebeneinander.

Ergebnis, das zählt: Jemand, der Log → Kalender → Auswertung durchklickt, muss
sofort erkennen, dass es dieselbe App ist. Nicht: "auf jeder Seite mal
was anderes ausprobiert".

---

## Die feste Grammatik (gilt auf JEDEM Screen, ändert sich nie)

Das ist der wichtigste Abschnitt dieses Briefings. Bevor irgendein Screen
angefasst wird, sollten diese vier Regeln als Konstanten/Tokens im Code stehen,
auf die sich alles andere bezieht.

### 1. Farbsystem
Eine Signalfarbe dominiert pro Kontext, nicht mehrere gleichzeitig bunt gemischt
(siehe Referenzen — Ojos Pardos: Lila/Braun, Shark: Neon-Grün, launch: Blau —
nie mehr als zwei Töne aktiv). Für Trainingslog konkret:
- **Blau** = Ausdauer-/Zeit-Metriken (Zeit, Distanz, Load)
- **Lila** = Kraft-/Intensitäts-Metriken (RPE, Zonen 4+5, Intensität)
- Bestehende Sport-Akzentfarben (Rad/Lauf Blau, Kraft Orange, Kampfsport Violett)
  bleiben für die Sportart-Kennzeichnung selbst bestehen — dieses neue Blau/Lila-Paar
  ist eine zusätzliche Ebene für *Metrik-Kategorien*, kein Ersatz.
- Grundfläche: helles, sehr schwach gesättigtes Off-White (kein reines Weiß).

### 2. Dithering-Grammatik
Eine einzige Pipeline, überall wiederverwendet — nicht pro Element neu erfunden.
Es existiert bereits ein fertiges, getestetes Modul dafür (siehe „Vorhandene
Bausteine" unten): Blue-Noise-Threshold, Downscale-Blur, Punktdichte statt
Punkt-Transparenz (jeder gezeichnete Punkt bleibt voll deckend).

Zwei Anwendungsfälle, beide über dieselbe Pipeline, nur mit anderen Parametern:
- **Statisch, an Ort und Stelle** (Logo, Sync-Icon, +-Button im Hintergrund):
  `density: 1.0` (kein Ausdünnen), grobe `grain`-Stufe, hoher Kontrast — Form
  bleibt zu jedem Zeitpunkt erkennbar, es „friert" im verpixelten Zustand ein,
  statt sich aufzulösen.
- **Datengetrieben** (Charts): `grain` deutlich größer als beim Logo — größere,
  klar sichtbare Pixel statt feinem Korn. Punktdichte kann hier Werte kodieren
  (dichteres Raster = höhere Last/Intensität) — Dithering als Teil der
  Datenvisualisierung, nicht nur Deko obendrüber.

### 3. Typografie-Regel
- Pixel-/Bitmap-Font **ausschließlich** für: die eine große Headline/Zahl pro
  Screen (siehe „variable Geste" unten) plus kurze Zahlen-Akzente.
- Alle Fließtexte, Labels, Achsenbeschriftungen, Formularfelder: die bestehende
  schlichte Grotesk. Niemals Pixel-Font im Fließtext — das war die Falle, die
  wir explizit vermeiden wollen.
- Gleiche Größenverhältnisse zwischen Pixel-Headline und Body auf jedem Screen,
  damit es sich wie ein System liest und nicht wie Zufall.

### 4. Papier-/Texturgefühl
Off-white Grundfläche app-weit gleich. Bereiche/Cards auf der Fläche bekommen
Papercut-Textur (Nutzer stellt transparente PNGs/SVGs bereit — siehe
„Assets" unten). Wichtig aus der Moodboard-Analyse: Die Textur liegt **in**
der Farbfläche selbst (Label ist gedithert/texturiert), nicht als separates
Rausch-Overlay obendrauf — das wirkt integrierter statt aufgesetzt.

---

## Was pro Screen variieren darf: die eine laute Geste

Jeder Screen bekommt **genau ein** dominantes Element, das die Poster-Geste
übernimmt — Größe statt Position erzeugt die Hierarchie (siehe Shark-Referenz:
riesige Zahl, nicht gepinnt, einfach durch Größe zuerst gelesen). Alles andere
auf dem Screen bekommt die Farbwelt/Textur/Typo aus der festen Grammatik, aber
keine zusätzliche eigene ausbrechende Geste. Ein Vorschlag, offen für Anpassung:

- **Log:** die heutige/aktuelle Einheit
- **Auswertung:** ACWR oder Load 7T, als große, ggf. selbst gedithert-verpixelte
  Zahl
- **Kalender:** der aktuelle Tag

Wenn auf einem Screen Cards, Charts, Labels und Hintergrund alle gleichzeitig
„brechen" (ausgefranste Kanten, Auflösung, Verpixelung), frisst sich das
gegenseitig auf. Eine Geste pro Screen, der Rest diszipliniert — das ist die
Regel, die das Poster-Prinzip trägt, kein Kompromiss an die Kreativität.

---

## Die einzelnen Punkte

### Logo, Sync- und +-Button verpixeln (Korrektur)
Kein Auflösen — feststehende, grobe Verpixelung im Hintergrund, Form bleibt
erkennbar. Siehe Dithering-Grammatik Punkt 2, „statischer" Anwendungsfall.

### Cards auflösen → freie Kacheln, horizontales Scrollen
Das am längsten diskutierte Thema, hier die verabschiedete Richtung:

- Cards verlassen das starre Grid, liegen als unterschiedlich große Kacheln
  frei auf der Fläche — gestaffelt/versetzt (siehe Ojos-Pardos-Referenz: versetzte
  Rechtecke), nicht gleichförmig aufgereiht. `scroll-snap` fürs Einrasten beim
  Wischen, damit es sich wie „durch ein Poster blättern" anfühlt, aber bedienbar
  bleibt.
- Größenhierarchie ersetzt Pinning: Die eine dominante Metrik (siehe oben) ist
  groß und wird zuerst gelesen, unabhängig von ihrer Position. Sekundäre
  Metriken (Ø-HF, Distanz, Höhenmeter etc.) sind kleinere Satelliten-Kacheln,
  die mit-scrollen — sie müssen nicht fixiert werden, weil die große Kachel
  die Orientierung übernimmt.
- **Mobil:** seitliches Scrollen zwischen den Kacheln, da kein Platz für alles
  gleichzeitig.
- **Desktop:** Fläche voll nutzen bei ausreichend Platz; bei kompaktem
  Fenster (schmaler Viewport) auf dasselbe seitliche Scrollen wie mobil
  zurückfallen — ein Verhalten, an der Fensterbreite gemessen, kein separates
  Desktop-Layout parallel pflegen.

### Hintergrund & Flächen
Siehe Papier-/Texturgefühl in der festen Grammatik. Labels auf blauem oder
lila Untergrund (Farbsystem-Regel), ebenfalls mit Textur in der Fläche.

### Font-Mix
Siehe Typografie-Regel in der festen Grammatik.

### Charts — Design-Überarbeitung
Neue Signalfarben (Blau/Lila-System) übernehmen, Dithering-Effekt einarbeiten
mit größeren Pixeln als beim Logo (siehe Dithering-Grammatik, Punkt
„datengetrieben"). Betrifft alle bestehenden Charts: Wochenvergleich,
Verteilung über Zeit, Workload-Progression, Aufschlüsselung nach Kategorie.

### KI-Chat
Bleibt bei Oldschool-Terminal-Optik, darf verstärkt werden — z. B.
Monospace-Font durchgängig, ggf. Blink-Cursor, reduzierte Farbigkeit passend
zur Off-White/Signalfarben-Palette. Kein Widerspruch zur restlichen Grammatik,
da Chat-Screens traditionell ohnehin reduzierter sind.

---

## Vorhandene Bausteine (bereits gebaut, bitte wiederverwenden)

Ein Scroll-Dithering-Modul für den Logo-Effekt existiert bereits, verifiziert
und produktionsreif (`dither-logo.js` + Assets, an anderer Stelle bereits
geliefert). Die Kern-Pipeline daraus (Blue-Noise-Threshold, Downscale-Blur,
dichte-basierte statt transparenz-basierte Auflösung) ist exakt das, was die
Dithering-Grammatik oben beschreibt — bitte als gemeinsame Basis für sowohl
den statischen Logo/Icon-Effekt als auch die Chart-Visualisierungen
extrahieren, statt zwei separate Implementierungen zu pflegen.

## Assets

Folgende Dateien werden vom Nutzer bereitgestellt bzw. liegen bereits im Repo:

- **`docs/moodboard/`** — die sieben Referenzbilder (Slapfunk-Records-Flyer,
  Ubicate-Event-Poster, launch.xyz, Shark-Agentur-Website, Wile-E.-Coyote-Poster,
  Ojos-Pardos-Flyer, moɪda-Kaffeebecher-Poster). Bitte direkt ansehen, nicht nur
  die Textbeschreibung unten nutzen — die Bildsprache (Korngröße, Kantenbrüche,
  Textur-in-der-Fläche) lässt sich aus den Bildern präziser ablesen als aus Worten.
- **`img/paper/`** — Papier-Hintergrund-PNGs (Papercut-Texturen, transparent)
  für die Off-White-Grundfläche und die texturierten Bereiche/Labels
- Weitere Fonts (Pixel-/Bitmap-Font für Headlines, Grotesk für Body) und
  ggf. zusätzliche SVG-Illustrationen werden noch ergänzt — Pfade dafür bitte
  konfigurierbar halten statt hart zu verdrahten, sobald sie feststehen

## Referenzen (Moodboard)

Sieben Referenzbilder wurden analysiert (Slapfunk-Records-Flyer, Ubicate-Event-Poster,
launch.xyz, Shark-Agentur-Website, Wile-E.-Coyote-Poster, Ojos-Pardos-Flyer,
moɪda-Kaffeebecher-Poster). Gemeinsame Merkmale, die oben eingeflossen sind:

- Dithering ersetzt das Bild, statt es zu dekorieren — grobe Punktraster,
  harter Schnitt zwischen gedithertem und flächigem Bereich
- Off-white Papier + eine dominante Signalfarbe, nicht mehrere gleichzeitig
- Pixel-Font streng auf Headlines/Akzente begrenzt, nie im Fließtext
- Formauflösung/ausbrechende Kanten als bewusste Ausnahme, nicht als
  Dauerzustand — genau eine laute Geste pro Komposition, alles andere
  diszipliniert daneben

---

## Vorgehen

Dies ist ein zusammenhängendes Design-System, keine Liste unabhängiger Fixes.
Sinnvoller Ablauf:

1. Feste Grammatik (Farb-Tokens, Dithering-Modul, Typo-Regeln, Textur-Handling)
   als gemeinsame Basis im Code anlegen, bevor einzelne Screens angefasst werden
2. Auswertung als ersten Screen umsetzen (meiste Chart-/Card-Komplexität,
   guter Test für die neue Grammatik)
3. Log, Kalender nach demselben Muster
4. KI-Chat und restliche Screens

Bei Unklarheiten zur „einen lauten Geste" pro Screen oder zur Kachel-Staffelung:
lieber Rückfrage stellen als eine Interpretation fest einbauen, die dann auf
allen Screens dupliziert wird.
