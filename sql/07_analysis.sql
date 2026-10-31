-- Migration 07 — analysis charts, the hot list, and the cadence/niche knobs of an hourly run.
-- Run it on EVERY database (fresh or old) after 01_core.sql, 02_media.sql and 03_functions.sql.
-- Safe to run again: every statement is `if not exists`.
--
-- 1. media can hold analysis charts: a new kind, a Vietnamese caption and a display position
-- 2. hot_videos: the hottest Bilibili videos and 国创 series of each run, flat (no join), for /analysis
-- 3. app_config: Bilibili series rankings, the niche (terms, exclusions, only-the-niche), a minimum duration for
--    long compilations, a search window of up to 180 days, and how often the heavy parts run

alter type media_kind_t add value if not exists 'analysis';
alter table media add column if not exists caption text;
alter table media add column if not exists position smallint;

create table if not exists hot_videos (
  run_id text not null references runs (id) on delete cascade,
  kind text not null default 'video' check (kind in ('video', 'series')),
  rank smallint not null check (rank between 1 and 50),   -- 1 = hottest within its kind
  video_id text not null,                                  -- 'bi_BV…' or 'bi_ss<season>'; no foreign key: videos get cleaned up
  platform text not null,
  title text not null,
  url text not null,
  channel_title text,                                      -- series: rating and episodes, e.g. '9.8分 · 全12话'
  views bigint not null default 0,                         -- series: total plays of the whole series
  duration_sec int,
  published_at timestamptz,
  niche boolean not null default false,                    -- matched app_config.niche_terms or a niche ranking
  viral_score double precision not null default 0,
  created_at timestamptz not null default now(),
  primary key (run_id, kind, rank)
);
create index if not exists hot_videos_created on hot_videos (created_at desc);
alter table hot_videos enable row level security;

alter table app_config add column if not exists bilibili_series_types int[] not null default '{}';
alter table app_config add column if not exists niche_terms text[] not null default '{}';
alter table app_config add column if not exists niche_boost double precision not null default 1
  check (niche_boost between 1 and 10);
alter table app_config add column if not exists youtube_search_every_hours int not null default 1
  check (youtube_search_every_hours between 1 and 24);
alter table app_config add column if not exists analysis_every_hours int not null default 1
  check (analysis_every_hours between 1 and 24);
alter table app_config add column if not exists niche_exclude_terms text[] not null default '{}';
alter table app_config add column if not exists niche_only boolean not null default false;
alter table app_config add column if not exists min_duration_sec int not null default 0
  check (min_duration_sec >= 0);
alter table app_config drop constraint if exists app_config_search_window_hours_check;
alter table app_config add constraint app_config_search_window_hours_check
  check (search_window_hours between 1 and 4320);
