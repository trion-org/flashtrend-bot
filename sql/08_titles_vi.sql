-- Migration 08 — video titles in Vietnamese for the hot list and the charts.
-- Run it on EVERY database (fresh or old) after 07_analysis.sql.
-- Safe to run again: every statement is `if not exists`.
--
-- 1. titles_vi: each title translated once (Gemini), keyed by the sha256 of the original title
-- 2. hot_videos.title_vi: the row's title in Vietnamese, so a reader needs no join

create table if not exists titles_vi (
  title_hash text primary key,                             -- 'sha256:' + sha256 of the original title
  title text not null,
  title_vi text not null,
  created_at timestamptz not null default now()
);
alter table titles_vi enable row level security;
alter table hot_videos add column if not exists title_vi text;   -- null = not translated: show title
