-- Paket F2 — Block-Ziele: Wochenzeit + Verteilung (docs/trainingslog-spec.md)
-- Im Supabase SQL-Editor ausführen. Additiv zu Paket F (2026-07-24-paket-f.sql), keine
-- bestehenden Spalten/Constraints angefasst. App-Fallback: fehlende Werte = NULL = "kein Ziel
-- gesetzt", das Budget-Widget fällt dann auf die rollierende 28-Tage-Ansicht zurück.

alter table blocks
  add column if not exists weekly_target_min integer,   -- Wochenzeit-Ziel in Minuten, NULL = kein Ziel
  add column if not exists sport_targets jsonb,          -- {"Lauf":{"pct":40,"count":3}, ...} — Keys = cfg.sports[].key
  add column if not exists zone_targets jsonb;           -- {"LIT":{"pct":80,"count":4}, "MIT":{...}, "HIT":{...}}
