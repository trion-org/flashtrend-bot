-- Migration 11 — estfstudio publishing: brands (one Fanpage ↔ one YouTube channel …) and the record of each job.
-- Run it on EVERY database (fresh or old) after 10_stories.sql.
-- Safe to run again: every statement is `if not exists` / `on conflict do nothing`.
--
-- A *brand* is one show identity (Mộng Ảnh, Xàm Xí Audio) published on several platforms at once. It owns AT MOST
-- ONE account per platform (primary key brand_id + platform) and an account belongs to ONE brand (unique platform +
-- native_id): a dub posted to a brand's Page goes to that brand's YouTube channel at the same time. Adding a
-- channel, a Page or a brand is adding rows. Keys never live here: `credential` names the entry of estfstudio's
-- .secrets/secrets.yml that holds the account's key.
--
-- dub_jobs / dub_posts keep what each day's jobs produced — TEXT ONLY (links, titles, descriptions, times); the
-- videos, covers and audio stay on the estfstudio machine. A restricted source (MissAV / 18+) is never recorded.

create table if not exists brands (
  id text primary key check (id ~ '^[a-z0-9][a-z0-9-]{0,39}$'),   -- slug = the Page's name in FB_PAGES
  title text not null,
  kind text not null default 'any' check (kind in ('film', 'audio', 'any')),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists brand_accounts (
  brand_id text not null references brands (id) on delete cascade,
  platform platform_t not null,                 -- facebook · youtube · tiktok …
  native_id text not null,                      -- the Page id / the channel id (UC…)
  credential text,                              -- name of the key entry in .secrets/secrets.yml (never the key)
  title text,
  handle text,                                  -- e.g. @MongAnh3D
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (brand_id, platform),             -- one account per platform per brand
  unique (platform, native_id)                  -- one brand per account
);

create table if not exists dub_jobs (
  id text primary key,                          -- the source video's id (file stem, e.g. BV1VbHm6LEim)
  kind text not null default 'film' check (kind in ('film', 'audio')),
  title text,                                   -- the film's name / the story's title
  source_url text,
  brand_id text references brands (id) on delete set null,
  parts int not null default 0,                 -- 0 = one video
  duration_s double precision,
  status text not null default 'dubbed' check (status in ('dubbed', 'published', 'partial', 'failed')),
  day text,                                     -- dd-MM-YYYY folder of workspace/ it was archived in
  meta jsonb not null default '{}'::jsonb,      -- voice, model, music … (small)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists dub_jobs_recent on dub_jobs (updated_at desc);

create table if not exists dub_posts (
  id text primary key,                          -- platform || ':' || native_id
  job_id text references dub_jobs (id) on delete cascade,
  platform platform_t not null,
  native_id text not null,
  url text not null,
  brand_id text references brands (id) on delete set null,
  account_id text,                              -- the Page id / channel id it went to
  kind text not null default 'video' check (kind in ('video', 'reel', 'photo')),
  part int not null default 0,
  parts int not null default 0,
  title text,
  description text,
  scheduled_at timestamptz,                     -- when it goes public (null = at once)
  status text not null default 'published' check (status in ('published', 'scheduled', 'draft', 'private')),
  twin_url text,                                -- the same video on the brand's other platform
  posted_at timestamptz not null default now(),
  unique (platform, native_id)
);
create index if not exists dub_posts_job on dub_posts (job_id, platform, part);
create index if not exists dub_posts_recent on dub_posts (posted_at desc);

alter table brands enable row level security;          -- service-role only (estfstudio's bot), like every table here
alter table brand_accounts enable row level security;
alter table dub_jobs enable row level security;
alter table dub_posts enable row level security;
