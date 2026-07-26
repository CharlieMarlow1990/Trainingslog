# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Trainingslog — a training-log PWA (German UI) for endurance/strength athletes. Live at
https://charliemarlow1990.github.io/Trainingslog/, served as static files via GitHub Pages.
There is no build step, no `package.json`, no bundler. The entire application is one file:
**`index.html`** (~9,600 lines: inline `<style>`, then inline `<script>`). Editing that file
*is* the deploy — commit and push to `main` and Pages serves it.

External runtime dependencies are loaded from CDN in `index.html`'s `<head>`: Chart.js 4.4.1,
JSZip, `@supabase/supabase-js@2`, Tabler Icons webfont, Google Fonts (Inter). No local npm
install is needed to run or edit the app.

## Running / testing locally

No dev server or build tooling exists. To work on it:

```bash
python3 -m http.server 8000    # or any static file server, from repo root
```

Then open `http://localhost:8000/index.html`. There is no automated test suite — verify changes
by loading the app in a browser and exercising the relevant screen (see the `run` skill for a
driven check). Auth is via Supabase GitHub OAuth (`sb.auth.signInWithOAuth`), so local testing
requires a real login against the project's Supabase instance.

## Architecture (all inside `index.html`)

**Data layer.** Session/workout records live in Supabase Postgres, accessed through a thin `DB`
object (`DB.getSessions`, `DB.addSession`, `DB.updateSession`, `DB.deleteSession`) wrapping
`sb.from('sessions')...`. `sb` is a `supabase-js` client created near the top of the script block.
Everything else — sport/zone config (`cfg`), wellness cache, Anthropic API key, in-progress form
drafts, GPX watch-folder import state — is cached in `localStorage` under `tlog_*` / feature-
specific keys, then reconciled with Supabase on load.

**App state** is a flat set of top-level `let` variables declared near the top of the script
(`sessions`, `wellness`, `cfg`, `templates`, `activePage`, various `*Chart` instances, per-screen
filter/offset state like `weekOffset`/`monthOffset`/`analyticsPeriod`). There is no framework,
no virtual DOM, no component tree — screens are rendered by imperative `render*()` functions that
rebuild DOM/innerHTML from state (`renderLog`, `renderCalendar`, `renderAnalytics`,
`renderLibrary`, `renderSettingsInline`, plus chart-specific renderers like
`renderAerobicEfficiencyChart`, `renderWorkloadChart`, `renderWeeklyTrendChart`).

**Navigation** is six screens (`log`, `calendar`, `analytics`, `library`, `ai`, `settings-page`),
each a `<div class="page" id="page-<key>">`. `showPage(key)` toggles the `.active` class, updates
the bottom-nav buttons, sets the header title from `pageTitles`, and calls that screen's
`render*()` function — there's no router/URL state.

**Training-load model** (`berechneWorkload(session)`) picks a workload metric by priority:
TSS from normalized power (cycling only, when `cfg.radMethod==='tss'`) → Edwards TRIMP from a
full HR time series → a previously stored Edwards value → Banister TRIMP from average HR → sRPE
→ a stored estimate for planned-but-unlogged sessions. **Cycling workload must stay TRIMP-based
by default** (`cfg.radMethod`), not power-based — power is used only for the separate EF
(aerobic efficiency / HR-decoupling) analysis in `computeEfficiency`/`computeHrDrift`. See
`docs/ef-decoupling.md` for the EF feature spec.

**AI chat / feedback hints** call the Anthropic API (`https://api.anthropic.com/v1/messages`)
directly from the browser using a user-supplied key stored in `localStorage['tlog_anthropic_key']`
(`generateFeedbackHint`, chat panel on the `ai` page). There is no backend proxy for this.

**Rendering grammar (design system).** The app follows a fixed "Y2K/Poster" visual grammar
documented in `docs/trainingslog-design-briefing.md`: off-white paper background, exactly two
signal colors (blue = endurance/time metrics, purple/lavender = intensity/strength metrics,
via the `--met-endurance*` / `--met-intensity*` CSS custom properties), one shared dithering
pipeline (`assets/dither-lib.js`, blue-noise threshold + density-encodes-value) reused for every
dithered chart/UI element, and a pixel/bitmap font (VCR OSD Mono) reserved *only* for one
poster-scale headline number per screen — never body text. When touching visuals, match this
grammar rather than introducing a one-off style; `design/` holds static HTML component
references (`design/_app.css`, `design/components/*.html`, `design/foundations/tokens.html`)
that should visually match what's shipped in `index.html`.

**`.design-sync/`** is state for an external Claude-Design sync tool, not app code — see
`.design-sync/NOTES.md` for the (currently stale) relationship between that external component
library and this repo.

## Garmin data sync (separate Python pipeline)

`garmin-ai/garmin_sync.py` (Python 3.11, deps in `garmin-ai/requirements.txt`) pulls the user's
own Garmin Connect data (workouts + wellness: sleep, HRV, resting HR, Body Battery, stress,
steps, training readiness) and writes it read-only into `garmin/`:

- `garmin/data.json` — machine-readable, fetched by the app for wellness widgets/backfill
- `garmin/wellness/YYYY-MM-DD.md`, `garmin/workouts/YYYY-MM-DD-*.md` — one note per day/workout

This runs via two GitHub Actions workflows, not locally in normal operation:

- `.github/workflows/garmin-auth.yml` — manual, one-time login that mints a long-lived token,
  stored as the `GARMIN_TOKENSTORE` repo secret (needs `GARMIN_EMAIL`/`GARMIN_PASSWORD` and,
  to auto-store the secret, a `GH_PAT`).
- `.github/workflows/garmin-sync.yml` — scheduled daily (05:00 UTC) plus manual dispatch with
  `days`/`activities_days` inputs; restores the token from the secret, runs the sync, and commits
  changed files under `garmin/` back to `main`.

Local run: `python garmin-ai/garmin_sync.py --auth` then `--days N` (see `garmin-ai/README.md`
for full setup). The index.html app calls `refreshGarminWellness()`/`backfillWorkload()` on load
to pull in whatever `garmin/data.json` last synced.

## Practical notes for editing `index.html`

- It's one file with no module boundaries — use `grep -n` for the function/variable you need
  rather than trying to read it top to bottom. Function names are descriptive and mostly
  German-adjacent (`berechneWorkload`, `renderKalender`-style names appear in German where they
  describe domain concepts, English for generic UI plumbing).
- Comments and UI copy are in German; keep new copy consistent with that.
- CSS custom properties (`:root{...}` near the top of the `<style>` block) are the source of
  truth for the color/spacing system — reuse tokens (`--met-endurance`, `--met-intensity`,
  `--paper*`, `--ink`, `--poster-size*`) instead of hardcoding values.
- State mutations should go through `DB.*` (for anything persisted to `sessions`) or update the
  matching `localStorage` key, then call the relevant `render*()` to reflect the change — there's
  no reactive binding.
