-- Migration 21 — a quota already lowered on Supabase is never raised by a later write.
-- Safe to run again. Additive (one column, three functions).
--
-- Several machines share one Kaggle account, one YouTube project, one Gemini key. A machine that read its value a
-- moment ago may write after another machine has used some of that quota; plain overwriting would hand the quota
-- back. So the three kinds of value that can be overwritten keep the value that says "more is used":
--   * gpu_quota_publish — hours left of a Kaggle account: within one week (same quota_refresh_at) the LOWER hours stay;
--     a new week (later refresh time) starts over. Returns what is stored and whether the write was taken.
--   * gpu_used_up_set   — "skip this account until": the LATER time stays.
--   * quota_block_set   — "this scope is out of quota until": the LATER time stays.
-- (Gemini request counts are already additive — gemini_count adds, never overwrites.)

alter table gpu_accounts add column if not exists quota_refresh_at timestamptz;

create or replace function gpu_quota_publish(p_name text, p_hours real, p_at timestamptz, p_refresh_at timestamptz)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  v gpu_accounts%rowtype;
  v_written boolean := false;
begin
  insert into gpu_accounts (kind, name) values ('kaggle', p_name) on conflict do nothing;
  select * into v from gpu_accounts where kind = 'kaggle' and name = p_name for update;
  if v.hours_left is null
     or (p_refresh_at is not null and (v.quota_refresh_at is null or p_refresh_at > v.quota_refresh_at))
     or p_hours <= v.hours_left then
    update gpu_accounts
       set hours_left = p_hours, quota_at = p_at,
           quota_refresh_at = coalesce(p_refresh_at, v.quota_refresh_at), updated_at = now()
     where kind = 'kaggle' and name = p_name;
    v_written := true;
    return jsonb_build_object('hours_left', p_hours, 'written', true);
  end if;
  return jsonb_build_object('hours_left', v.hours_left, 'written', false);
end;
$$;

create or replace function gpu_used_up_set(p_name text, p_until timestamptz, p_reason text)
returns timestamptz
language plpgsql
set search_path = public
as $$
declare
  v_until timestamptz;
begin
  insert into gpu_accounts (kind, name) values ('kaggle', p_name) on conflict do nothing;
  update gpu_accounts
     set used_up_until = p_until, used_up_reason = p_reason, updated_at = now()
   where kind = 'kaggle' and name = p_name
     and (used_up_until is null or used_up_until < p_until);
  select used_up_until into v_until from gpu_accounts where kind = 'kaggle' and name = p_name;
  return v_until;
end;
$$;

create or replace function quota_block_set(p_scope text, p_until timestamptz, p_reason text, p_holder text)
returns timestamptz
language plpgsql
set search_path = public
as $$
declare
  v_until timestamptz;
begin
  insert into quota_blocks as b (scope, blocked_until, reason, holder)
  values (p_scope, p_until, p_reason, p_holder)
  on conflict (scope) do update
    set blocked_until = excluded.blocked_until, reason = excluded.reason, holder = excluded.holder, updated_at = now()
    where b.blocked_until < excluded.blocked_until
  returning b.blocked_until into v_until;
  if v_until is null then
    select blocked_until into v_until from quota_blocks where scope = p_scope;   -- the stored one was later: kept
  end if;
  return v_until;
end;
$$;

revoke all on function gpu_quota_publish(text, real, timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function gpu_used_up_set(text, timestamptz, text) from public, anon, authenticated;
revoke all on function quota_block_set(text, timestamptz, text, text) from public, anon, authenticated;
grant execute on function gpu_quota_publish(text, real, timestamptz, timestamptz) to service_role;
grant execute on function gpu_used_up_set(text, timestamptz, text) to service_role;
grant execute on function quota_block_set(text, timestamptz, text, text) to service_role;

notify pgrst, 'reload schema';
