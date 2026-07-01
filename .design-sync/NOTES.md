# design-sync notes

## Repo shape

This repo has no `package.json`, no JS framework, no build (`index.html` is a single static
file). `design/` holds static HTML mockups with inline `<style>` (matching `design/_app.css`
exactly) — a visual style guide, not compiled component source. There is nothing here for the
converter (storybook/package shapes) to bundle — treat this as permanently off-envelope for the
full component pipeline.

## Target project

`fb410ea3-4f3e-47b3-a499-36e26a1cfb43` ("Trainingslog Design System", owned by Charlie) already
existed with a full React component library (`Button`, `Badge`, `Pill`, `StatCard`,
`ActivityRow`, `HeroCard`) built independently inside Claude Design from an uploaded HTML
reference — not from this git repo. That reference used an old violet/purple palette that the
app has since replaced with a warm "Paper/Editorial" theme (terracotta accent, paper
background). See `guidelines/PAPER_EDITORIAL_NOTICE.md` in the project for the full writeup.

2026-07-01: added 7 `guidelines/app-*.card.html` cards (tokens, buttons, badges, cards,
chart-legend, metrics, tabs) synced directly from `design/foundations/tokens.html` and
`design/components/*.html`, plus a notice card + markdown flagging the palette conflict.
Purely additive — nothing in `components/core/*`, `tokens/*.css`, or `styles.css` was touched.

## Open item

The existing `components/core/*` and `tokens/*.css` still reflect the old violet palette and
should be retokenized/rebuilt to match Paper/Editorial before this project is fully in sync with
the shipped app again. That's a deliberate follow-up task, not something this pass attempted.
