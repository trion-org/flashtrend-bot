-- Migration 16 — which estfstudio bot, on which machine, holds which borrowed GPU account.
-- Safe to run again: `if not exists` / `create or replace`.
--
-- estfstudio borrows free Kaggle GPUs, each reached through a zrok tunnel. Several bots (the film bot, the audio
-- bot) on one or more machines share the same Kaggle and zrok accounts, and two of them on one account break each
-- other: a second kernel push on a Kaggle account stops the session it already runs, and two kernels cannot serve
-- from one zrok identity. So estfstudio LEASES an account before it uses it:
--   * gpu_claim() takes or renews the lease atomically — it succeeds when nobody holds the account, the holder is
--     the caller, or the last lease ran out (a holder that died leaves a lease that ends about when its GPU does);
--   * gpu_release() gives it back when the worker is shut down.
-- `holder` is "<host>:<bot>" (e.g. "studio-pc:audio"). The table also keeps each account's last known GPU hours and
-- why it is skipped (no GPU: a phone-less account), so every machine picks from the same picture.
-- TEXT ONLY — never a key, a token or a share secret.

create table if not exists gpu_accounts (
  kind text not null check (kind in ('kaggle', 'zrok', 'build')),
  name text not null,                           -- the Kaggle username / the zrok account's label
  holder text,                                  -- who holds it now ("<host>:<bot>"); null = free
  lease_until timestamptz,                      -- the lease ends then unless renewed
  status text not null default 'idle' check (status in ('idle', 'starting', 'ready')),
  slot integer,                                 -- the holder's fleet slot (0 = its main worker)
  base_url text,                                -- the holder's local tunnel end (informational)
  hours_left real,                              -- Kaggle's own count, last read
  quota_at timestamptz,                         -- when it was read
  used_up_until timestamptz,                    -- skipped until then
  used_up_reason text check (used_up_reason in ('quota', 'no_gpu')),
  updated_at timestamptz not null default now(),
  primary key (kind, name)
);
create index if not exists gpu_accounts_holder on gpu_accounts (holder) where holder is not null;

alter table gpu_accounts enable row level security;   -- service-role only, like every table here

create or replace function gpu_claim(p_kind text, p_name text, p_holder text, p_ttl_s integer,
                                     p_status text default 'starting', p_slot integer default null,
                                     p_base_url text default null)
returns boolean
language plpgsql
set search_path = public
as $$
begin
  insert into gpu_accounts (kind, name) values (p_kind, p_name) on conflict do nothing;
  update gpu_accounts
     set holder = p_holder,
         lease_until = now() + make_interval(secs => p_ttl_s),
         status = p_status,
         slot = p_slot,
         base_url = p_base_url,
         updated_at = now()
   where kind = p_kind and name = p_name
     and (holder is null or holder = p_holder or lease_until is null or lease_until < now());
  return found;
end;
$$;

create or replace function gpu_release(p_kind text, p_name text, p_holder text)
returns boolean
language plpgsql
set search_path = public
as $$
begin
  update gpu_accounts
     set holder = null, lease_until = null, status = 'idle', slot = null, base_url = null, updated_at = now()
   where kind = p_kind and name = p_name and holder = p_holder;
  return found;
end;
$$;

revoke all on function gpu_claim(text, text, text, integer, text, integer, text) from public, anon, authenticated;
revoke all on function gpu_release(text, text, text) from public, anon, authenticated;
grant execute on function gpu_claim(text, text, text, integer, text, integer, text) to service_role;
grant execute on function gpu_release(text, text, text) to service_role;
