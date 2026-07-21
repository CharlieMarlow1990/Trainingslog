# Aufgabe: ASCII-Effekt in Session-Karte einbauen

## Ziel
In der farbigen Session-Karte (siehe bestehende Render-Funktion der "Aktuelle Einheiten"-Karte)
sollen zwei Elemente als **gefülltes ASCII** (Dichte-Rampe, nicht Outline) erscheinen und beim
Aufklappen der Karte **tippend** (spaltenweiser Sweep) eingeblendet werden:

1. **Dauer der Einheit** als gefüllte ASCII-Ziffern (z. B. `0:40`), datengetrieben aus dem
   `duration`-Feld der Session.
2. **Sport-Symbol** als Bild→ASCII (kein handgezeichnetes Icon), pro Sportart aus einer kleinen
   Bildquelle gerendert.

## Einbaustelle
Zwischen den Markern `<!-- ASCII_HERO_START -->` und `<!-- ASCII_HERO_END -->` in `index.html`.
Trigger für den Tipp-Effekt: die bestehende `toggleCard()`-Funktion beim Aufklappen dieser Karte.

## Verhalten
- Rendering vollständig im Browser via `<canvas>`, **keine externe Bibliothek**.
- Dichte-Rampe: `" .,-~:;=!*#$@"` (Space = Hintergrund/transparent).
- Zeichen-Seitenverhältnis: Zeilenzahl = `round(cols * (h/w) * 0.5)`.
- Farbe über CSS-Variablen (bestehende Theming-Konvention), Default = dunkle Kartenschrift auf
  Kartenfarbe. Kein Hardcoding von Farben im JS.
- Sweep: pro Frame eine Spalte mehr freigeben (`line.slice(0, c)`), links→rechts.

## Konventionen (unbedingt einhalten)
- Single-File `index.html`, GitHub Pages, UTF-8. **Alle Emojis/Sonderzeichen als HTML-Entities.**
- Config (Rampe, Farben, Schwellen) in `localStorage` bzw. `cfg`, nicht im Code fest verdrahten.
- Sport→Bildquelle als Map, analog zu bestehender Sport-Konfiguration in `cfg.sportZones`.
- DB-Zugriffe über das zentrale `DB`-Objekt; keine neuen direkten Supabase-Calls.
- Theming nur über CSS-Variablen, keine strukturellen HTML-Änderungen an bestehenden Karten.

## Referenz-Implementierung (getestet, aus dem ASCII-Studio)
Die drei Kernfunktionen unten sind erprobt und können übernommen/angepasst werden.

```js
const RAMP = " .,-~:;=!*#$@";
const CHAR_AR = 0.5; // Zeichenzelle ist ~2x so hoch wie breit

// Beliebige drawable (HTMLImageElement ODER Canvas) -> ASCII-Zeilen
function sourceToAscii(src, opt = {}) {
  const { cols = 40, gamma = 0.8, contrast = 1.0, brightness = 0,
          threshold = 0.10, blur = 1.0, invert = false } = opt;
  const rows = Math.max(1, Math.round(cols * (src.height / src.width) * CHAR_AR));
  // Blur auf Zwischen-Canvas, dann runterskalieren (mittelt)
  const tmp = document.createElement('canvas');
  const s = Math.min(1, 900 / src.width);
  tmp.width = Math.max(1, Math.round(src.width * s));
  tmp.height = Math.max(1, Math.round(src.height * s));
  const tc = tmp.getContext('2d');
  tc.filter = blur > 0 ? `blur(${blur}px)` : 'none';
  tc.drawImage(src, 0, 0, tmp.width, tmp.height);
  const cv = document.createElement('canvas'); cv.width = cols; cv.height = rows;
  const cx = cv.getContext('2d'); cx.imageSmoothingEnabled = true;
  cx.drawImage(tmp, 0, 0, cols, rows);
  const d = cx.getImageData(0, 0, cols, rows).data;
  const lines = [];
  for (let y = 0; y < rows; y++) {
    let line = "";
    for (let x = 0; x < cols; x++) {
      const i = (y * cols + x) * 4;
      let v = (0.299*d[i] + 0.587*d[i+1] + 0.114*d[i+2]) / 255;
      v = (v - 0.5) * contrast + 0.5 + brightness / 255;
      v = Math.min(1, Math.max(0, v));
      let ink = invert ? v : (1 - v);
      ink = Math.pow(ink, gamma);
      if (ink < threshold) { line += " "; continue; }
      let idx = Math.round(ink * (RAMP.length - 1));
      line += RAMP[Math.min(RAMP.length - 1, Math.max(1, idx))];
    }
    lines.push(line.replace(/\s+$/, ''));
  }
  // leere Randzeilen trimmen
  while (lines.length && !lines[0].trim()) lines.shift();
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  return lines;
}

// Text (z. B. Dauer "0:40") -> gefülltes ASCII, gleiche Pipeline
function textToAscii(text, opt = {}) {
  const fs = 170, pad = Math.round(fs * 0.25), fam = opt.font || 'sans-serif';
  const meas = document.createElement('canvas').getContext('2d');
  meas.font = `bold ${fs}px ${fam}`;
  let w = 0; for (const ch of text) w += meas.measureText(ch).width;
  w = Math.ceil(w) + pad * 2; const h = Math.round(fs * 1.4);
  const c = document.createElement('canvas'); c.width = Math.max(10, w); c.height = h;
  const x = c.getContext('2d');
  x.fillStyle = "#fff"; x.fillRect(0, 0, c.width, h);
  x.fillStyle = "#000"; x.font = `bold ${fs}px ${fam}`; x.textBaseline = "middle";
  let cx0 = pad; for (const ch of text) { x.fillText(ch, cx0, h/2); cx0 += meas.measureText(ch).width; }
  return sourceToAscii(c, opt);
}

// Tippender Spalten-Sweep in ein <pre>-Element
function typewriteSweep(el, lines, speed = 14) {
  clearInterval(el._sweep);
  const w = Math.max(...lines.map(l => l.length));
  let c = 0; el.textContent = "";
  el._sweep = setInterval(() => {
    c++;
    el.textContent = lines.map(l => l.slice(0, c)).join("\n");
    if (c >= w) clearInterval(el._sweep);
  }, speed);
}
```

## Verdrahtung (Beispiel)
```js
// Bilder pro Sportart einmalig laden (oder als kleine Assets im Repo)
const SPORT_IMG = { lauf: 'assets/lauf.png', rad: 'assets/rad.png', kraft: 'assets/kraft.png' };

async function renderCardAscii(session, timeEl, iconEl) {
  // Zeit (datengetrieben)
  const timeLines = textToAscii(formatDuration(session.duration), { cols: 40, threshold: 0.05 });
  // Sportbild
  const img = new Image();
  img.onload = () => {
    const iconLines = sourceToAscii(img, { cols: 24, gamma: 0.8, threshold: 0.12 });
    typewriteSweep(iconEl, iconLines, 10);
    typewriteSweep(timeEl, timeLines, 16);
  };
  img.src = SPORT_IMG[session.sport] || SPORT_IMG.lauf;
}
```

## Abnahmekriterien
- [ ] Zeit rendert gefüllt (Dichte-Rampe), korrekt aus `session.duration`.
- [ ] Sport-Symbol stammt aus Bildquelle, Hintergrund transparent (Schwelle greift).
- [ ] Beim Aufklappen läuft der Sweep; erneutes Aufklappen wiederholt ihn sauber.
- [ ] Farben ausschließlich über CSS-Variablen; kein Emoji/Sonderzeichen ohne HTML-Entity.
- [ ] Keine externe Bibliothek, kein Bild-Upload nach außen, keine neuen Supabase-Calls.
- [ ] Auf schmalen Screens kein Layout-Bruch (font-size per clamp() an Kartenbreite koppeln).
```
