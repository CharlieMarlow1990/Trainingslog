-- Paket A1 — Ghost-Sessions (docs/trainingslog-spec.md)
-- Im Supabase SQL-Editor ausführen. Die App läuft dank Spalten-Fallbacks auch
-- ohne diese Migration, dann aber ohne persistierten status/planned_ref.

alter table sessions
  add column if not exists status text not null default 'done'
    check (status in ('planned','done')),
  add column if not exists planned_ref uuid references sessions(id) on delete set null,
  add column if not exists block_id uuid;  -- siehe Paket F

create index if not exists sessions_status_date_idx on sessions (status, date);

-- Bestandsdaten: bestehendes planned-Boolean in status spiegeln.
update sessions set status='planned' where planned is true and status='done';
