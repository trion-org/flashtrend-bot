-- Migration 17 — quotas and reservations that several estfstudio machines must see together.
-- Safe to run again: `if not exists` / `create or replace`. Additive only — nothing existing is touched.
--
-- estfstudio runs on several machines, each looking after its own Fanpages, but they share the same Gemini API
-- keys, the same YouTube OAuth projects and (per Page) the Facebook publishing queue. Until now each machine
-- counted those in a local file, so two of them each believed they had the whole quota. This keeps one picture:
--   * gemini_usage   — the day's requests per API key (by FINGERPRINT, never the key) and model, and whether
--                      the model is spent on that key; gemini_count() adds to it atomically;
--   * fb_slots       — the publish times (unix seconds) a machine has reserved on a Page for a post still
--                      uploading — a video that is still processing is not yet in Facebook's own queue, so two
--                      machines posting to one Page could otherwise be given the same slot; fb_slot_claim() takes
--                      one atomically, a lease that lapses frees it;
--   * quota_blocks   — "this scope is out of quota until then" (a YouTube project's daily units, a channel's
--                      upload allowance), so the other machines stop trying instead of each hitting the error.
-- TEXT AND NUMBERS ONLY — never an API key, a token or a secret. Service-role only, like every table here.

create table if not exists gemini_usage (
  key_tag text not null,                        -- sha256(key)[:8]: names a key without revealing it
  model text not null,
  day date not null,                            -- the Pacific day Google counts the free tier by
  requests integer not null default 0,
  spent boolean not null default false,         -- Google said today's requests of this model are used up
  updated_at timestamptz not null default now(),
  primary key (key_tag, model, day)
);
alter table gemini_usage enable row level security;

create table if not exists fb_slots (
  page_id text not null,
  slot_at bigint not null,                      -- the reserved publish time, unix seconds
  holder text not null,                         -- "<host>:<bot>"
  lease_until timestamptz not null,             -- an upload that never finished frees its slot after this
  updated_at timestamptz not null default now(),
  primary key (page_id, slot_at)
);
alter table fb_slots enable row level security;

create table if not exists quota_blocks (
  scope text primary key,                       -- e.g. "youtube-project:<client id fingerprint>", "youtube-channel:<name>"
  blocked_until timestamptz not null,
  reason text,
  holder text,
  updated_at timestamptz not null default now()
);
alter table quota_blocks enable row level security;

-- add p_n requests to a key's day and return the new total: {"requests": n, "spent": bool}
create or replace function gemini_count(p_tag text, p_model text, p_day date, p_n integer default 1)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  v_requests integer;
  v_spent boolean;
begin
  insert into gemini_usage as u (key_tag, model, day, requests)
  values (p_tag, p_model, p_day, greatest(p_n, 0))
  on conflict (key_tag, model, day)
  do update set requests = u.requests + greatest(p_n, 0), updated_at = now()
  returning u.requests, u.spent into v_requests, v_spent;
  delete from gemini_usage where day < p_day - 7;      -- the table stays a few dozen rows
  return jsonb_build_object('requests', v_requests, 'spent', v_spent);
end;
$$;

create or replace function gemini_spend(p_tag text, p_model text, p_day date)
returns boolean
language plpgsql
set search_path = public
as $$
begin
  insert into gemini_usage as u (key_tag, model, day, spent) values (p_tag, p_model, p_day, true)
  on conflict (key_tag, model, day) do update set spent = true, updated_at = now();
  return true;
end;
$$;

-- take (or renew) the slot for p_holder: true when it was free, ours already, or its lease had lapsed
create or replace function fb_slot_claim(p_page text, p_slot bigint, p_holder text, p_ttl_s integer)
returns boolean
language plpgsql
set search_path = public
as $$
begin
  delete from fb_slots where lease_until < now();
  insert into fb_slots as s (page_id, slot_at, holder, lease_until)
  values (p_page, p_slot, p_holder, now() + make_interval(secs => p_ttl_s))
  on conflict (page_id, slot_at)
  do update set holder = p_holder, lease_until = now() + make_interval(secs => p_ttl_s), updated_at = now()
  where s.holder = p_holder or s.lease_until < now();
  return found;
end;
$$;

create or replace function fb_slot_release(p_page text, p_slot bigint, p_holder text)
returns boolean
language plpgsql
set search_path = public
as $$
begin
  delete from fb_slots where page_id = p_page and slot_at = p_slot and holder = p_holder;
  return found;
end;
$$;

revoke all on function gemini_count(text, text, date, integer) from public, anon, authenticated;
revoke all on function gemini_spend(text, text, date) from public, anon, authenticated;
revoke all on function fb_slot_claim(text, bigint, text, integer) from public, anon, authenticated;
revoke all on function fb_slot_release(text, bigint, text) from public, anon, authenticated;
grant execute on function gemini_count(text, text, date, integer) to service_role;
grant execute on function gemini_spend(text, text, date) to service_role;
grant execute on function fb_slot_claim(text, bigint, text, integer) to service_role;
grant execute on function fb_slot_release(text, bigint, text) to service_role;
