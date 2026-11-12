-- Migration 18 — which machine is polling which Telegram bot token.
-- Safe to run again: `if not exists` / `create or replace`. Additive only — nothing existing is touched.
--
-- Telegram serves ONE long-polling client per bot token: a second copy of the same bot (on another machine that
-- shares the secrets) only produces `Conflict: terminated by other getUpdates request` and steals the chat's
-- commands from the first. estfstudio has two bots (film = estfstudio-bot, audio = estfstudio-bot-audio) that may be
-- started on any machine, so a bot leases its token before it polls:
--   * bot_leases      — one row per token FINGERPRINT (sha256(token)[:8], never the token): who holds it, until when;
--   * bot_claim()     — take or renew atomically: succeeds when free, ours already, or the lease lapsed; when it
--                       fails it says who holds it, so the other machine can tell the user;
--   * bot_release()   — give it back on a clean stop.
-- A holder that dies leaves a lease that lapses by itself (the bot renews every minute, the lease lasts a few).
-- TEXT ONLY — never a token. Service-role only, like every table here.

create table if not exists bot_leases (
  token_tag text primary key,                   -- sha256(token)[:8]
  role text not null,                           -- film | audio | all (informational)
  holder text not null,                         -- "<host>:<bot>"
  lease_until timestamptz not null,
  updated_at timestamptz not null default now()
);
alter table bot_leases enable row level security;

create or replace function bot_claim(p_tag text, p_role text, p_holder text, p_ttl_s integer)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  v_holder text;
  v_until timestamptz;
begin
  insert into bot_leases as b (token_tag, role, holder, lease_until)
  values (p_tag, p_role, p_holder, now() + make_interval(secs => p_ttl_s))
  on conflict (token_tag)
  do update set role = p_role, holder = p_holder, lease_until = now() + make_interval(secs => p_ttl_s),
                updated_at = now()
  where b.holder = p_holder or b.lease_until < now();
  if found then
    return jsonb_build_object('ok', true, 'holder', p_holder);
  end if;
  select holder, lease_until into v_holder, v_until from bot_leases where token_tag = p_tag;
  return jsonb_build_object('ok', false, 'holder', v_holder, 'until', extract(epoch from v_until));
end;
$$;

create or replace function bot_release(p_tag text, p_holder text)
returns boolean
language plpgsql
set search_path = public
as $$
begin
  delete from bot_leases where token_tag = p_tag and holder = p_holder;
  return found;
end;
$$;

revoke all on function bot_claim(text, text, text, integer) from public, anon, authenticated;
revoke all on function bot_release(text, text) from public, anon, authenticated;
grant execute on function bot_claim(text, text, text, integer) to service_role;
grant execute on function bot_release(text, text) to service_role;

notify pgrst, 'reload schema';   -- so PostgREST sees the new functions without a restart
