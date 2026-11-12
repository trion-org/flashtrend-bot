-- Migration 20 — the Gemini cost per minute of video lives in Supabase too (no local gemini_usage.json any more).
-- Safe to run again. Additive.
--
-- estfstudio learns how many Gemini requests a minute of translated video costs (the running totals below) to plan
-- how many keys / how much quota a film needs. It was kept beside the day's counts in workspace/gemini_usage.json;
-- every machine now adds to ONE total here. gemini_history_add() adds atomically and returns the new totals.
-- NUMBERS ONLY.

create table if not exists gemini_history (
  id integer primary key default 1 check (id = 1),     -- a single row
  minutes double precision not null default 0,
  requests bigint not null default 0,
  updated_at timestamptz not null default now()
);
alter table gemini_history enable row level security;

create or replace function gemini_history_add(p_minutes double precision, p_requests bigint)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  v_minutes double precision;
  v_requests bigint;
begin
  insert into gemini_history as h (id, minutes, requests)
  values (1, greatest(p_minutes, 0), greatest(p_requests, 0))
  on conflict (id)
  do update set minutes = h.minutes + greatest(p_minutes, 0), requests = h.requests + greatest(p_requests, 0),
                updated_at = now()
  returning h.minutes, h.requests into v_minutes, v_requests;
  return jsonb_build_object('minutes', v_minutes, 'requests', v_requests);
end;
$$;

revoke all on function gemini_history_add(double precision, bigint) from public, anon, authenticated;
grant execute on function gemini_history_add(double precision, bigint) to service_role;

notify pgrst, 'reload schema';
