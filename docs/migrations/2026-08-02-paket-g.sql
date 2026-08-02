-- Paket G — Blockvorlagen, Dosisbänder, Erhaltungsreize, Makrobilanz
-- (docs/PAKET_G_Blockvorlagen.md). Im Supabase SQL-Editor ausführen.
-- Additiv zu Paket F (2026-07-24-paket-f.sql) und F2 (2026-07-28-paket-f2-blockziele.sql),
-- keine bestehenden Spalten/Constraints angefasst. Alle Spalten nullable:
-- Blöcke ohne template_id verhalten sich exakt wie vor Paket G.
--
-- App-Fallback: solange die Migration nicht gelaufen ist, strippt die App die neuen
-- Spalten aus Insert/Update (G_BLOCK_COLS bzw. LEGACY_OPT_COLS in index.html) — die
-- App bleibt lauffähig, die neuen Felder werden nur nicht persistiert.

alter table blocks
  add column if not exists template_id      text,     -- BLOCK_TEMPLATES[].id, NULL = freier Block
  add column if not exists template_version int,      -- beim Anlegen eingefroren, nie nachgezogen
  add column if not exists dose_bands       jsonb,    -- {"zone.HIT.count":{"min":3,"opt":4,"ceil":5,"lock":"fixed"}, ...}
  add column if not exists floors           jsonb,    -- [{"key":"run_km","op":">=","value":12,"unit":"km_per_7d","lock":"bounded"}, ...]
  add column if not exists modified         boolean default false,  -- Wert außerhalb fixed/bounded gesetzt
  add column if not exists modified_fields  text[],   -- betroffene Dosisband-Pfade
  add column if not exists exit_booking     jsonb;    -- {completedAt,complianceP,litDebtWeeks,lockUntil,entryOverride}

-- Kraft-Typ je Einheit. Trägt den Erhaltungsreiz-Floor "strength_heavy":
-- nur 'max' (Maximalkraft) erfüllt ihn. NULL = ungepflegt → Floor gilt als
-- "nicht prüfbar", nicht als verletzt (siehe evaluateFloors in index.html).
-- Metabolische Belastung wird als eigene Sportart 'Capacity' geführt, nicht hier.
alter table sessions
  add column if not exists strength_type text;        -- 'max' | 'hyp' | 'ausdauer' | NULL
