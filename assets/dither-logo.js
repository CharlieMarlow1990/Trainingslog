/**
 * DitherLogo
 * ----------
 * Scroll-driven dithering effect for a fixed logo.
 *
 * The logo starts as a solid, crisp shape, then dissolves into a blue-noise
 * dither pattern as the user scrolls. The perceived transparency comes purely
 * from DOT DENSITY (fewer dots survive the threshold test) — every dot that
 * IS drawn stays fully opaque. Scrolling back reverses the effect exactly,
 * because everything is a pure function of scroll position (no animation state).
 *
 * Pipeline per frame:
 *   1. Blur the source alpha field  -> halo bleeds beyond the original glyphs
 *   2. Downsample to the dither grid
 *   3. Per cell: v = alpha * density; v += (threshold - 0.5) * ditherStrength
 *   4. Quantize v to `colorLevels` discrete steps
 *   5. v <= 0 -> transparent, else solid mix(background, ink, v)
 *
 * Usage:
 *   import { DitherLogo } from './dither-logo.js';
 *   const fx = new DitherLogo({
 *     canvas: document.querySelector('#logo-canvas'),
 *     logoSrc: '/assets/training-log-logo.png',
 *     blueNoiseSrc: '/assets/bluenoise64.png',
 *   });
 *   await fx.init();
 *   // later, e.g. on route change / unmount:
 *   fx.destroy();
 */

import {
  clamp,
  hexToRgb,
  loadImage,
  ditherField,
  thresholdFn,
  loadBlueNoise,
} from './dither-lib.js';

const DEFAULTS = {
  // --- assets ---
  logoSrc: '/assets/training-log-logo.png',
  blueNoiseSrc: '/assets/bluenoise64.png',

  // --- static mode ---
  // true = eingefrorene Verpixelung (Dithering-Grammatik, statischer Fall):
  // kein Scroll-Listener, kein Auflösen — es wird einmal der `start`-Zustand
  // gerendert und dabei bleibt es. Form bleibt jederzeit erkennbar.
  static: false,

  // --- working canvas ---
  // Keep this close to the actual on-screen display size. If the internal
  // resolution is much larger than the rendered size, the browser downscales
  // the dither pattern and the dots visually merge back into smooth edges.
  width: 600,
  height: 380,
  // Padding inside the canvas so the blur halo has room to spread instead of
  // being clipped at the canvas edge.
  padX: 100,
  padY: 100,

  // --- scroll mapping ---
  // Fraction of viewport height over which the whole effect plays out.
  effectVh: 0.85,
  // Fraction of that range (0..1) where nothing happens yet — logo stays solid.
  hold: 0.05,
  // Fraction of that range used to cross-fade from the solid shape into the
  // dither pattern. Without this the switch is visible as a hard "tipping point".
  transition: 0.06,

  // --- dither curve (linear between these two endpoints) ---
  start: { density: 1.0, grain: 1, blur: 9 },
  end: { density: 0.0, grain: 1, blur: 98 },

  // --- dither look ---
  // 'blue' | 'white' | 'bayer2' | 'bayer4' | 'bayer8'
  // Blue noise: randomly distributed but evenly spaced. Avoids both the
  // clumping of white noise and the visible repeating grid of Bayer.
  thresholdMode: 'blue',
  // 2 = strictly binary on/off. Higher values keep every dot opaque but allow
  // intermediate solid tones, which preserves the logo's chrome shading.
  colorLevels: 2,
  ditherStrength: 1.0,
  // Alpha values below this (0..1) are forced to 0 before the threshold test,
  // killing stray specks far outside the glyphs caused by source noise.
  noiseFloor: 0,

  // --- colors ---
  ink: '#f5f0e1',
  background: '#14161a',

  // --- shadow ---
  // Versetzter Schlagschatten, der DIESELBE Dither-/Solid-Grammatik wie das Logo
  // benutzt (identische Dot-Positionen, nur umgefärbt). Liegt HINTER dem Logo und
  // ist versetzt — dadurch scheinen seine Pixel durch die Pixel-Lücken des Logos.
  // null = kein Schatten. { color, offsetX, offsetY, opacity }.
  shadow: null,

  // --- optional extras ---
  chromaticAberration: 0, // px, offsets R/B channels apart
  postDitherBlur: 0, // px, CSS blur on the finished pattern

  // --- behaviour ---
  // Element whose scroll drives the effect. Defaults to the window.
  scrollContainer: null,
  // If true, respects prefers-reduced-motion by pinning to the solid state.
  respectReducedMotion: true,
};

export class DitherLogo {
  constructor(options = {}) {
    if (!options.canvas) throw new Error('DitherLogo: `canvas` is required');

    this.opts = {
      ...DEFAULTS,
      ...options,
      start: { ...DEFAULTS.start, ...(options.start || {}) },
      end: { ...DEFAULTS.end, ...(options.end || {}) },
      shadow: options.shadow
        ? {
            color: '#9BE7A8',
            offsetX: 6,
            offsetY: 6,
            opacity: 0.45,
            ...options.shadow,
          }
        : null,
    };

    this.canvas = this.opts.canvas;
    this.ctx = this.canvas.getContext('2d');
    this.W = this.opts.width;
    this.H = this.opts.height;
    this.canvas.width = this.W;
    this.canvas.height = this.H;

    this.ready = false;
    this.ticking = false;
    this.blueNoise = null;
    this.destroyed = false;

    // Source: the logo converted to an "ink density" alpha field.
    this.srcCanvas = document.createElement('canvas');
    this.srcCanvas.width = this.W;
    this.srcCanvas.height = this.H;
    this.srcCtx = this.srcCanvas.getContext('2d');

    this._onScroll = this._onScroll.bind(this);
    this._onResize = this._onResize.bind(this);
  }

  async init() {
    const [logoImg, bn] = await Promise.all([
      loadImage(this.opts.logoSrc),
      this.opts.thresholdMode === 'blue'
        ? loadBlueNoise(this.opts.blueNoiseSrc)
        : Promise.resolve(null),
    ]);

    this.blueNoise = bn;
    this._ingestLogo(logoImg);

    this.ready = true;
    if (this.opts.static) {
      // Statischer Fall der Dithering-Grammatik: einmal im start-Zustand
      // einfrieren, keine Scroll-Kopplung.
      this.renderStatic();
    } else {
      this._attach();
      this.render(this.getProgress());
    }
    return this;
  }

  /** Rendert den eingefrorenen Dither-Zustand (start-Parameter) genau einmal. */
  renderStatic() {
    if (!this.ready || this.destroyed) return;
    const c = this.opts.start;
    const dith = this._applyAberration(
      this._renderDither(c.density, c.grain, c.blur)
    );
    this._composite(dith, false);
  }

  /**
   * Färbt eine gerenderte Ebene (Dither-Dots oder Solid-Form) auf `color` um,
   * ohne die Alpha-Maske zu verändern. So behält der Schatten exakt dieselben
   * Pixel-/Dot-Positionen wie das Logo — nur die Farbe wechselt.
   */
  _tint(source, color) {
    const out = document.createElement('canvas');
    out.width = this.W;
    out.height = this.H;
    const octx = out.getContext('2d');
    octx.imageSmoothingEnabled = false;
    octx.drawImage(source, 0, 0);
    octx.globalCompositeOperation = 'source-in';
    octx.fillStyle = color;
    octx.fillRect(0, 0, this.W, this.H);
    return out;
  }

  /**
   * Setzt die fertige Logo-Ebene aufs Canvas: erst der versetzte, umgefärbte
   * Schatten (falls konfiguriert), dann das Logo darüber. Weil das Logo dieselbe
   * Ebene ist, deckt es den Schatten nur dort ab, wo es Pixel hat — durch die
   * Lücken scheint der Schatten hindurch.
   */
  _composite(content, smooth) {
    const ctx = this.ctx;
    ctx.globalAlpha = 1;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, this.W, this.H);

    const sh = this.opts.shadow;
    if (sh) {
      ctx.globalAlpha = sh.opacity;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(this._tint(content, sh.color), sh.offsetX, sh.offsetY);
    }

    ctx.globalAlpha = 1;
    ctx.imageSmoothingEnabled = smooth;
    ctx.drawImage(content, 0, 0);
  }

  /**
   * Converts the logo into an alpha-only "ink density" field:
   * existing alpha (shape) multiplied by darkness (shading). Works whether the
   * source has real transparency or is a flat image on a light background.
   */
  _ingestLogo(img) {
    const rawW = img.naturalWidth;
    const rawH = img.naturalHeight;
    const rc = document.createElement('canvas');
    rc.width = rawW;
    rc.height = rawH;
    const rctx = rc.getContext('2d');
    rctx.drawImage(img, 0, 0);

    const idata = rctx.getImageData(0, 0, rawW, rawH);
    const d = idata.data;
    for (let i = 0; i < d.length; i += 4) {
      const existingAlpha = d[i + 3] / 255;
      const lum = (d[i] + d[i + 1] + d[i + 2]) / 3 / 255;
      const ink = existingAlpha * clamp((1 - lum) * 1.3, 0, 1);
      d[i] = 20;
      d[i + 1] = 20;
      d[i + 2] = 20;
      d[i + 3] = Math.round(clamp(ink, 0, 1) * 255);
    }
    rctx.putImageData(idata, 0, 0);

    const logoW = this.W - this.opts.padX * 2;
    const logoH = this.H - this.opts.padY * 2;
    const scale = Math.min(logoW / rawW, logoH / rawH);
    const fitW = rawW * scale;
    const fitH = rawH * scale;

    this.srcCtx.clearRect(0, 0, this.W, this.H);
    this.srcCtx.drawImage(
      rc,
      this.opts.padX + (logoW - fitW) / 2,
      this.opts.padY + (logoH - fitH) / 2,
      fitW,
      fitH
    );
  }

  /**
   * The solid shape tinted to the ink color. Used for the hold phase and as
   * the "from" side of the cross-fade, so the transition never changes hue —
   * only smoothness.
   */
  _renderSolid() {
    const out = document.createElement('canvas');
    out.width = this.W;
    out.height = this.H;
    const octx = out.getContext('2d');
    octx.fillStyle = this.opts.ink;
    octx.fillRect(0, 0, this.W, this.H);
    octx.globalCompositeOperation = 'destination-in';
    octx.drawImage(this.srcCanvas, 0, 0);
    return out;
  }

  _renderDither(density, grain, blurPx) {
    // Delegiert an die gemeinsame Pipeline (dither-lib) — eine Implementierung
    // für Logo/Icons UND Chart-Füllungen (Design-Briefing, Dithering-Grammatik).
    return ditherField(this.srcCanvas, {
      density,
      grain,
      blur: blurPx,
      ink: this.opts.ink,
      background: this.opts.background,
      colorLevels: this.opts.colorLevels,
      ditherStrength: this.opts.ditherStrength,
      noiseFloor: this.opts.noiseFloor,
      threshold: thresholdFn(this.opts.thresholdMode, this.blueNoise),
    });
  }

  _applyAberration(source) {
    const amount = this.opts.chromaticAberration;
    if (amount <= 0) return source;

    const out = document.createElement('canvas');
    out.width = this.W;
    out.height = this.H;
    const octx = out.getContext('2d');
    octx.imageSmoothingEnabled = false;
    octx.globalCompositeOperation = 'lighter';

    const chans = [
      { dx: -amount, mask: 'rgb(255,0,0)' },
      { dx: 0, mask: 'rgb(0,255,0)' },
      { dx: amount, mask: 'rgb(0,0,255)' },
    ];
    for (const ch of chans) {
      const tmp = document.createElement('canvas');
      tmp.width = this.W;
      tmp.height = this.H;
      const tctx = tmp.getContext('2d');
      tctx.imageSmoothingEnabled = false;
      tctx.drawImage(source, 0, 0);
      tctx.globalCompositeOperation = 'multiply';
      tctx.fillStyle = ch.mask;
      tctx.fillRect(0, 0, this.W, this.H);
      tctx.globalCompositeOperation = 'destination-in';
      tctx.drawImage(source, 0, 0);
      octx.drawImage(tmp, ch.dx, 0);
    }
    return out;
  }

  _curve(t) {
    const { start, end } = this.opts;
    return {
      density: start.density + (end.density - start.density) * t,
      grain: Math.round(start.grain + (end.grain - start.grain) * t),
      blur: start.blur + (end.blur - start.blur) * t,
    };
  }

  getProgress() {
    if (this._reducedMotion()) return 0;
    const el = this.opts.scrollContainer;
    const scrollTop = el ? el.scrollTop : window.scrollY;
    const vh = el ? el.clientHeight : window.innerHeight;
    return clamp(scrollTop / (vh * this.opts.effectVh), 0, 1);
  }

  _reducedMotion() {
    return (
      this.opts.respectReducedMotion &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
  }

  render(progress) {
    if (!this.ready || this.destroyed) return;
    const { hold, transition } = this.opts;

    this.canvas.style.filter =
      this.opts.postDitherBlur > 0
        ? `blur(${this.opts.postDitherBlur}px)`
        : 'none';

    // Phase 1 — hold: solid shape, no effect.
    if (progress <= hold) {
      this._composite(this._renderSolid(), true);
      return;
    }

    const transEnd = hold + transition;

    // Phase 2 — cross-fade solid -> dither, so there is no visible jump.
    if (progress <= transEnd) {
      const localT = (progress - hold) / transition;
      const c = this._curve(0);
      const dith = this._applyAberration(
        this._renderDither(c.density, c.grain, c.blur)
      );

      // Auf eine Zwischen-Ebene mischen, damit Logo UND Schatten denselben
      // Cross-Fade-Zustand teilen (der Schatten färbt genau diese Ebene um).
      const content = document.createElement('canvas');
      content.width = this.W;
      content.height = this.H;
      const cx = content.getContext('2d');
      cx.globalAlpha = 1 - localT;
      cx.imageSmoothingEnabled = true;
      cx.drawImage(this._renderSolid(), 0, 0);
      cx.globalAlpha = localT;
      cx.imageSmoothingEnabled = false;
      cx.drawImage(dith, 0, 0);

      this._composite(content, false);
      return;
    }

    // Phase 3 — dither curve, remapped so it still ends exactly at progress=1.
    const t = (progress - transEnd) / (1 - transEnd);
    const c = this._curve(clamp(t, 0, 1));
    const dith = this._applyAberration(
      this._renderDither(c.density, c.grain, c.blur)
    );

    this._composite(dith, false);
  }

  _onScroll() {
    if (this.ticking) return;
    this.ticking = true;
    requestAnimationFrame(() => {
      this.render(this.getProgress());
      this.ticking = false;
    });
  }

  _onResize() {
    this.render(this.getProgress());
  }

  _attach() {
    const target = this.opts.scrollContainer || window;
    target.addEventListener('scroll', this._onScroll, { passive: true });
    window.addEventListener('resize', this._onResize);
  }

  /** Update options at runtime, e.g. theme changes. */
  setOptions(patch) {
    this.opts = { ...this.opts, ...patch };
    this.render(this.getProgress());
  }

  destroy() {
    const target = this.opts.scrollContainer || window;
    target.removeEventListener('scroll', this._onScroll);
    window.removeEventListener('resize', this._onResize);
    this.destroyed = true;
  }
}

export default DitherLogo;
