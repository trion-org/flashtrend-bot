-- 22_zrok_quota — what each zrok account moved in the last 24 h, counted by every machine (estfstudio).
--
-- A zrok account's transfer cap is per account, not per machine, and the same accounts are used by several machines
-- (and by ystudio). Each machine used to estimate the use from its own `zrok access` process only, so it believed
-- the account had the whole allowance. Now every machine adds the bytes its tunnel moved here, and reads the sum.
--
-- Bytes are kept in 10-minute buckets per account (a few hundred rows at most); a bucket older than 26 h is dropped
-- by the next write. Additive and idempotent: it touches nothing that exists, so a running bot is not affected.
-- The blocks of an account zrok refused ride the existing `quota_blocks` table (scope `zrok:<account>`, 17 + 21).

create table if not exists zrok_usage (
  account text not null,                        -- the zrok account's label (secrets.yml `zrok:` name)
  bucket timestamptz not null,                  -- the start of the 10-minute bucket the bytes were moved in
  bytes bigint not null default 0,              -- payload bytes (what `zrok access` read, not read + written)
  updated_at timestamptz not null default now(),
  primary key (account, bucket)
);
alter table zrok_usage enable row level security;   -- service-role only, like every table here

create or replace function zrok_usage_add(p_account text, p_bytes bigint, p_at timestamptz default now())
returns boolean
language plpgsql
set search_path = public
as $$
declare
  v_bucket timestamptz := to_timestamp(floor(extract(epoch from p_at) / 600) * 600);
begin
  if p_bytes <= 0 then
    return true;
  end if;
  insert into zrok_usage as u (account, bucket, bytes)
  values (p_account, v_bucket, p_bytes)
  on conflict (account, bucket)
  do update set bytes = u.bytes + excluded.bytes, updated_at = now();   -- atomic: two machines never overwrite each other
  delete from zrok_usage where bucket < now() - interval '26 hours';
  return true;
end;
$$;

revoke all on function zrok_usage_add(text, bigint, timestamptz) from public, anon, authenticated;
grant execute on function zrok_usage_add(text, bigint, timestamptz) to service_role;

notify pgrst, 'reload schema';
