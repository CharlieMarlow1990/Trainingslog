-- Paket I2 — Einheiten-Infos: Trainingstyp je Einheit
-- Im Supabase SQL-Editor ausführen. Additiv zu Paket G (2026-08-02-paket-g.sql),
-- keine bestehenden Spalten/Constraints angefasst. Die Spalte ist nullable:
-- Einheiten ohne session_type verhalten sich exakt wie vor Paket I2.
--
-- App-Fallback: solange die Migration nicht gelaufen ist, strippt die App die neue
-- Spalte aus Insert/Update (I2_SESSION_COLS in index.html) — die App bleibt lauffähig,
-- der Trainingstyp wird nur nicht persistiert. Die Stufe liegt bewusst VOR der
-- Paket-G-Stufe, damit eine fehlende session_type-Spalte nicht auch strength_type
-- und die Workload-/EF-Felder mit wegwirft.

-- Trainingstyp je Einheit. Vokabular je Sportart in SESSION_TYPES (index.html),
-- absichtlich getrennt gehalten: 'Sweetspot' ergibt beim Laufen so wenig Sinn wie
-- 'Longrun' auf dem Rad. Kraft führt seinen Reiz weiter in strength_type (Paket G),
-- deshalb steht dort kein session_type. Rein beschreibend — geht NICHT in
-- berechneWorkload ein und verändert keine Belastungsrechnung.
alter table sessions
  add column if not exists session_type text;  -- 'dauerlauf' | 'intervall' | … | NULL
