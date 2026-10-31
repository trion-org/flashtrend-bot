-- FlashTrend schema v1 (docs/03 · DDL). Paste into the Supabase SQL Editor and Run.
-- Generated from tools/docs/03-du-lieu.archify.md; keep the two in step.

-- Chỉ dùng giờ Việt Nam: SQL Editor và now() hiển thị +07
alter database postgres set timezone to 'Asia/Ho_Chi_Minh';

create extension if not exists vector;

create type platform_t as enum (
  'youtube', 'tiktok', 'facebook', 'bilibili', 'douyin'
);
create type run_trigger_t as enum ('schedule', 'workflow_dispatch');
create type run_status_t as enum ('running', 'ok', 'error');
create type idea_status_t as enum ('new', 'seen', 'used', 'rejected');
create type feedback_label_t as enum (
  'useful', 'not_useful', 'duplicate', 'used'
);
create type publish_status_t as enum (
  'queued', 'uploaded', 'scheduled', 'failed'
);
create type privacy_t as enum ('private', 'unlisted', 'public');

create table app_config (
  id smallint primary key default 1 check (id = 1),
  schema_version int not null default 1,
  regions text[] not null default array['VN'],
  keywords text[] not null,
  z_threshold double precision not null default 1.5,
  cosine_threshold double precision not null default 0.70,
  history_cosine_threshold double precision not null default 0.80,
  decay_lambda double precision not null default 0.05,
  engagement_like_w double precision not null default 1.5,
  engagement_comment_w double precision not null default 3.0,
  bayes_c int not null default 1000,
  min_cohort_n int not null default 20,
  snapshot_ttl_days int not null default 90,
  llm_enabled boolean not null default true,
  updated_at timestamptz not null default now()
);

create table channels (
  id text primary key,
  platform platform_t not null,
  native_id text not null,
  title text not null,
  subscriber_count bigint,
  video_count int,
  channel_avg_views double precision not null,
  fetched_at timestamptz not null,
  stale_after timestamptz not null,
  unique (platform, native_id)
);

create table videos (
  id text primary key,
  platform platform_t not null,
  native_id text not null,
  url text not null,
  title text not null,
  description text not null default '',
  published_at timestamptz not null,
  channel_id text not null references channels (id),
  duration_sec int,
  thumbnail_url text,
  last_views bigint not null default 0,
  last_likes bigint not null default 0,
  last_comments bigint not null default 0,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  last_run_id text,
  transcript_excerpt text,
  unique (platform, native_id)
);

create table runs (
  id text primary key,
  schema_version int not null default 1,
  trigger run_trigger_t not null,
  git_sha text not null,
  region text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  status run_status_t not null default 'running',
  error jsonb,
  collected int not null default 0,
  scored int not null default 0,
  outliers int not null default 0,
  ideas_count int not null default 0,
  cohort_n int,
  cohort_mu_ratio double precision,
  cohort_sigma_ratio double precision,
  cohort_median_engagement double precision,
  duration_ms int,
  chart_path text
);

create table snapshots (
  video_id text not null references videos (id),
  run_id text not null references runs (id),
  captured_at timestamptz not null,
  views bigint not null,
  likes bigint not null,
  comments bigint not null,
  expire_at timestamptz not null,
  primary key (video_id, run_id)
);

create table candidates (
  run_id text not null references runs (id) on delete cascade,
  video_id text not null references videos (id),
  platform platform_t not null,
  title text not null,
  url text not null,
  channel_id text not null references channels (id),
  views bigint not null,
  likes bigint not null,
  comments bigint not null,
  age_hours double precision not null,
  channel_avg_views double precision not null,
  performance_ratio double precision not null,
  z_score double precision not null,
  engagement double precision not null,
  time_decay double precision not null,
  velocity double precision,
  acceleration double precision,
  early_flag boolean not null default false,
  viral_score double precision not null,
  passed_z boolean not null,
  query_tag text,
  expire_at timestamptz not null,
  primary key (run_id, video_id)
);

create table ideas (
  run_id text not null references runs (id) on delete cascade,
  video_id text not null references videos (id),
  platform platform_t not null,
  title text not null,
  url text not null,
  published_at timestamptz not null,
  views bigint not null,
  likes bigint not null,
  comments bigint not null,
  channel_title text not null,
  channel_id text not null references channels (id),
  channel_avg_views double precision not null,
  performance_ratio double precision not null,
  z_score double precision not null,
  engagement double precision not null,
  time_decay double precision not null,
  viral_score double precision not null,
  duplicates_count int not null default 0,
  novelty_score double precision,
  cluster_id text not null,
  llm jsonb,
  status idea_status_t not null default 'new',
  created_at timestamptz not null default now(),
  primary key (run_id, video_id)
);

create table embeddings (
  video_id text primary key references videos (id),
  model text not null default 'all-MiniLM-L6-v2',
  dim int not null default 384 check (dim = 384),
  text_hash text not null,
  source text not null check (source in ('title', 'title+transcript')),
  embedding vector(384) not null,
  updated_at timestamptz not null default now()
);

create table feedback (
  run_id text not null,
  video_id text not null,
  label feedback_label_t not null,
  labeled_at timestamptz not null default now(),
  note text,
  primary key (run_id, video_id),
  foreign key (run_id, video_id) references ideas (run_id, video_id)
);

create table publish_jobs (
  id text primary key,
  run_id text not null,
  video_id text not null,
  status publish_status_t not null default 'queued',
  youtube_video_id text,
  publish_at timestamptz,
  privacy_status privacy_t not null default 'private',
  made_for_kids boolean not null,
  error jsonb,
  foreign key (run_id, video_id) references ideas (run_id, video_id)
);

create index snapshots_video_time on snapshots (video_id, captured_at desc);
create index candidates_run_score on candidates (run_id, passed_z, viral_score desc);
create index ideas_run_rank on ideas (run_id, viral_score desc);
create index embeddings_updated on embeddings (updated_at desc);
create index embeddings_hnsw on embeddings
  using hnsw (embedding vector_cosine_ops);

alter table app_config enable row level security;
alter table channels enable row level security;
alter table videos enable row level security;
alter table runs enable row level security;
alter table snapshots enable row level security;
alter table candidates enable row level security;
alter table ideas enable row level security;
alter table embeddings enable row level security;
alter table feedback enable row level security;
alter table publish_jobs enable row level security;

-- Columns proposed on docs page 04 (relaxed threshold, niche feed knobs, Bilibili)
alter table app_config add column relaxed_z_threshold double precision not null default 0.5;
alter table runs add column z_threshold_used double precision;
alter table app_config add column chart_enabled boolean not null default true;
alter table app_config add column search_window_hours int not null default 48
  check (search_window_hours between 1 and 4320);
alter table app_config add column bilibili_keywords text[] not null default '{}';
