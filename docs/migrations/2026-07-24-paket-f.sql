-- Paket F1 — Blöcke (docs/trainingslog-spec.md)
-- Im Supabase SQL-Editor ausführen. Die App läuft dank Tabellen-Fallback (DB.getBlocks
-- liefert [] bei fehlender Tabelle) auch ohne diese Migration, dann aber ohne Blöcke.
-- sessions.block_id existiert bereits aus Paket A (2026-07-24-paket-a.sql); die Zuordnung
-- wird abgeleitet (resolveBlockForDate), nicht fixiert.

create table if not exists blocks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text not null,
  intention text not null check (intention in ('LIT','MIT','HIT','Deload','Frei')),
  starts_on date not null,
  ends_on date not null,
  color text,
  note text,
  created_at timestamptz default now()
);
create index if not exists blocks_range_idx on blocks (user_id, starts_on, ends_on);

-- RLS analog zu templates: jeder Nutzer sieht/bearbeitet nur eigene Blöcke.
alter table blocks enable row level security;
do $$ begin
  create policy blocks_owner on blocks
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
exception when duplicate_object then null; end $$;
