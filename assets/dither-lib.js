/**
 * dither-lib
 * ----------
 * Gemeinsamer Kern der Dithering-Grammatik (Design-Briefing): Blue-Noise-
 * Threshold, Downscale-Blur, dichte-basierte statt transparenz-basierte
 * Auflösung — jeder gezeichnete Punkt bleibt voll deckend.
 *
 * Eine Pipeline, zwei Anwendungsfälle:
 *   (a) statisch/eingefroren  — Logo, Sync-Icon, +-Button (DitherLogo mit static:true)
 *   (b) datengetrieben        — Chart-Füllungen über makeDitherTile()
 *       (größeres Grain als beim Logo; Punktdichte kann Werte kodieren)
 *
 * Alle Asset-Pfade bleiben Optionen (Briefing: konfigurierbar halten).
 */

export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export function hexToRgb(hex) {
  const v = parseInt(hex.slice(1), 16);
  return { r: (v >> 16) & 255, g: (v >> 8) & 255, b: v & 255 };
}

export function whiteNoiseThreshold(x, y) {
  let n = (x * 374761393 + y * 668265263) | 0;
  n = ((n ^ (n >> 13)) * 1274126177) | 0;
  n = n ^ (n >> 16);
  return ((n >>> 0) % 10000) / 10000;
}

// Vorberechnete Bayer-Matrizen (geordnetes Dithering).
export const BAYER = {
  bayer2: { size: 2, data: [0, 2, 3, 1].map((v) => (v + 0.5) / 4) },
  bayer4: {
    size: 4,
    data: [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map(
      (v) => (v + 0.5) / 16
    ),
  },
  bayer8: {
    size: 8,
    data: [
      0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4,
      36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22, 3, 35, 11, 43, 1, 33,
      9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7, 39, 13, 45, 5, 37, 63,
      31, 55, 23, 61, 29, 53, 21,
    ].map((v) => (v + 0.5) / 64),
  },
};

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${src}`));
    img.src = src;
  });
}

// --- Blue Noise (gecacht pro URL) --------------------------------------------

const _bnCache = new Map();

/** Lädt eine Blue-Noise-Textur und liefert {size, data:Float32Array}. */
export function loadBlueNoise(src = 'assets/bluenoise64.png') {
  if (!_bnCache.has(src)) {
    _bnCache.set(
      src,
      loadImage(src).then((img) => {
        const size = img.naturalWidth;
        const c = document.createElement('canvas');
        c.width = size;
        c.height = size;
        const cx = c.getContext('2d');
        cx.drawImage(img, 0, 0);
        const d = cx.getImageData(0, 0, size, size).data;
        const out = new Float32Array(size * size);
        for (let i = 0; i < size * size; i++) out[i] = d[i * 4] / 255;
        return { size, data: out };
      })
    );
  }
  return _bnCache.get(src);
}

/** Threshold-Funktion für einen Modus ('blue' | 'bayer2/4/8' | 'white'). */
export function thresholdFn(mode, blueNoise) {
  if (mode === 'blue' && blueNoise) {
    const s = blueNoise.size;
    const d = blueNoise.data;
    return (x, y) => d[(y % s) * s + (x % s)];
  }
  const b = BAYER[mode];
  if (b) return (x, y) => b.data[(y % b.size) * b.size + (x % b.size)];
  return whiteNoiseThreshold;
}

// --- Kern-Pipeline -----------------------------------------------------------

/**
 * Downscale-then-upscale-Blur. Bewusst kein ctx.filter — das ist auf
 * Offscreen-Canvases in manchen Browsern (älteres iOS-Safari) unzuverlässig.
 */
export function boxBlur(source, W, H, blurPx) {
  const out = document.createElement('canvas');
  out.width = W;
  out.height = H;
  const octx = out.getContext('2d');
  if (blurPx <= 0) {
    octx.drawImage(source, 0, 0);
    return out;
  }
  const factor = clamp(1 - blurPx / 101, 0.008, 1);
  const tW = Math.max(1, Math.round(W * factor));
  const tH = Math.max(1, Math.round(H * factor));
  const temp = document.createElement('canvas');
  temp.width = tW;
  temp.height = tH;
  const tctx = temp.getContext('2d');
  tctx.imageSmoothingEnabled = true;
  tctx.imageSmoothingQuality = 'high';
  tctx.drawImage(source, 0, 0, tW, tH);
  octx.imageSmoothingEnabled = true;
  octx.imageSmoothingQuality = 'high';
  octx.drawImage(temp, 0, 0, W, H);
  return out;
}

/**
 * Dithert ein Alpha-Feld (srcCanvas) in ein Punktraster.
 * Pro Zelle: v = alpha·density; v += (threshold−0.5)·strength; quantisiert auf
 * colorLevels. v<=0 → transparent, sonst voll deckendes mix(background, ink, v).
 * Liefert ein Canvas in Quellgröße (Nearest-Neighbor hochskaliert).
 */
export function ditherField(srcCanvas, opts = {}) {
  const {
    density = 1,
    grain = 1,
    blur = 0,
    ink = '#1B1B18',
    background = '#EAE9E4',
    colorLevels = 2,
    ditherStrength = 1,
    noiseFloor = 0,
    threshold = whiteNoiseThreshold,
  } = opts;

  const W = srcCanvas.width;
  const H = srcCanvas.height;
  const inkRgb = hexToRgb(ink);
  const bgRgb = hexToRgb(background);

  const blurred = boxBlur(srcCanvas, W, H, blur);
  const pixelSize = Math.max(1, grain);
  const smallW = Math.max(1, Math.ceil(W / pixelSize));
  const smallH = Math.max(1, Math.ceil(H / pixelSize));

  const small = document.createElement('canvas');
  small.width = smallW;
  small.height = smallH;
  const sctx = small.getContext('2d');
  sctx.imageSmoothingEnabled = true;
  sctx.drawImage(blurred, 0, 0, smallW, smallH);

  const imgData = sctx.getImageData(0, 0, smallW, smallH);
  const d = imgData.data;

  for (let y = 0; y < smallH; y++) {
    for (let x = 0; x < smallW; x++) {
      const i = (y * smallW + x) * 4;
      let a = d[i + 3] / 255;
      if (a < noiseFloor) a = 0;

      let v = a * density;
      v += (threshold(x, y) - 0.5) * ditherStrength;
      v = Math.floor(clamp(v, 0, 1) * (colorLevels - 1) + 0.5) / (colorLevels - 1);

      if (v <= 0) {
        d[i + 3] = 0;
      } else {
        d[i] = Math.round(bgRgb.r + (inkRgb.r - bgRgb.r) * v);
        d[i + 1] = Math.round(bgRgb.g + (inkRgb.g - bgRgb.g) * v);
        d[i + 2] = Math.round(bgRgb.b + (inkRgb.b - bgRgb.b) * v);
        d[i + 3] = 255;
      }
    }
  }
  sctx.putImageData(imgData, 0, 0);

  const out = document.createElement('canvas');
  out.width = W;
  out.height = H;
  const octx = out.getContext('2d');
  octx.imageSmoothingEnabled = false;
  octx.drawImage(small, 0, 0, smallW, smallH, 0, 0, W, H);
  return out;
}

// --- Datengetriebene Kacheln (Chart-Füllungen) -------------------------------

const _tileCache = new Map();

/**
 * Wiederholbare Dither-Kachel: gleichmäßiges Feld der gegebenen Dichte.
 * Dichte kodiert den Datenwert (dichteres Raster = höhere Last/Intensität).
 * grain deutlich größer als beim Logo wählen (Briefing: sichtbare Pixel).
 */
export function makeDitherTile(opts = {}) {
  const {
    size = 64,
    grain = 6,
    density = 0.5,
    ink = '#2441FF',
    background = 'transparent',
    blueNoise = null,
    thresholdMode = 'blue',
  } = opts;

  const key = `${size}|${grain}|${density}|${ink}|${background}|${thresholdMode}`;
  if (_tileCache.has(key)) return _tileCache.get(key);

  // Volles Alpha-Feld — die Dichte kommt allein aus dem Threshold-Test.
  const field = document.createElement('canvas');
  field.width = size;
  field.height = size;
  const fctx = field.getContext('2d');
  fctx.fillStyle = '#000';
  fctx.fillRect(0, 0, size, size);

  const transparent = background === 'transparent' || background == null;
  const tile = ditherField(field, {
    density,
    grain,
    ink,
    // Bei transparentem Hintergrund: colorLevels 2 → jeder Punkt ist reines Ink.
    background: transparent ? ink : background,
    colorLevels: 2,
    threshold: thresholdFn(thresholdMode, blueNoise),
  });

  if (!transparent) {
    // Deckenden Grund unter das Raster legen
    const solid = document.createElement('canvas');
    solid.width = size;
    solid.height = size;
    const sctx = solid.getContext('2d');
    sctx.fillStyle = background;
    sctx.fillRect(0, 0, size, size);
    sctx.drawImage(tile, 0, 0);
    _tileCache.set(key, solid);
    return solid;
  }
  _tileCache.set(key, tile);
  return tile;
}

// --- Geditherte Poster-Headline ----------------------------------------------

/**
 * Rendert Text (Pixel-Font) als grob geditherte, eingefrorene Poster-Zahl.
 * Wichtig: vorher `document.fonts.load()` abwarten, sonst rastert der Fallback.
 */
export function renderDitherText(canvas, opts = {}) {
  const {
    text = '',
    font = '"VCR OSD Mono", monospace',
    px = 160,
    grain = 4,
    blur = 2,
    density = 1,
    ink = '#2441FF',
    blueNoise = null,
    thresholdMode = 'blue',
    pad = Math.ceil(px * 0.15),
  } = opts;

  // Textmaße bestimmen
  const meas = document.createElement('canvas').getContext('2d');
  meas.font = `${px}px ${font}`;
  const m = meas.measureText(text);
  const W = Math.ceil(m.width) + pad * 2;
  const H = Math.ceil(px * 1.2) + pad * 2;

  const field = document.createElement('canvas');
  field.width = W;
  field.height = H;
  const fctx = field.getContext('2d');
  fctx.font = `${px}px ${font}`;
  fctx.textBaseline = 'top';
  fctx.fillStyle = '#000';
  fctx.fillText(text, pad, pad);

  const dith = ditherField(field, {
    density,
    grain,
    blur,
    ink,
    background: ink,
    colorLevels: 2,
    noiseFloor: 0.12,
    threshold: thresholdFn(thresholdMode, blueNoise),
  });

  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, W, H);
  ctx.drawImage(dith, 0, 0);
  return { width: W, height: H };
}
