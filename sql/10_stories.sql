-- Migration 10 — the story library of estfstudio's "audio" posts (/posts → 🎧 Audio → chọn truyện).
-- Run it on EVERY database (fresh or old) after 09_run_modes.sql.
-- Safe to run again: every statement is `if not exists`.
--
-- A story is a text file the admin sends to the estfstudio Telegram bot (/story). The file itself lives on the
-- third-party upload host (S3_URL, like the chart images — docs/07); Supabase keeps only its public link, its
-- sha256 (one row per file content) and what a picker needs to show: the title and the length. estfstudio reads
-- the text back from `url` when a story is narrated, and counts how often each one was used.

create table if not exists stories (
  id text primary key,                          -- 'st_' || left(sha256, 16)
  owner text not null default 'estfstudio' check (owner in ('flashtrend', 'estfstudio')),
  title text not null check (length(title) between 1 and 200),
  url text not null,                            -- public URL the upload host answered
  host text not null default 'nobinobi',
  sha256 text not null unique,                  -- of the uploaded file: the same text is never stored twice
  bytes int not null check (bytes > 0),
  chars int not null check (chars > 0),         -- characters of the story text (≈ narration length)
  filename text,                                -- the name it was sent under
  lang text not null default 'vi',
  added_by text,                                -- Telegram user id of the admin who sent it
  alive boolean not null default true,          -- false once the host no longer serves `url`
  used_count int not null default 0,
  last_used_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists stories_recent on stories (created_at desc) where alive;
alter table stories enable row level security;  -- service-role only (estfstudio's bot), like every table here
