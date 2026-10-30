-- media: image links on the third-party host (docs/03 · media). Run after 01_core.sql.

create type media_kind_t as enum ('thumbnail', 'chart', 'cover');

create table media (
  id text primary key,                    -- 'img_' || left(sha256, 16)
  owner text not null check (owner in ('flashtrend', 'estfstudio')),
  kind media_kind_t not null,
  url text not null,                      -- URL công khai do image host trả về
  host text not null default 'nobinobi',
  sha256 text not null unique,
  bytes int not null check (bytes <= 2000000),
  width int,
  height int,
  video_id text references videos (id),
  run_id text references runs (id) on delete set null,
  alive boolean not null default true,    -- false khi HEAD url trả 404
  checked_at timestamptz,
  created_at timestamptz not null default now()
);
create index media_video on media (video_id);
alter table media enable row level security;
alter table runs add column chart_media_id text references media (id);
