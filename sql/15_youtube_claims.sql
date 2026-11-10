-- Migration 15 — the audit log of YouTube copyright claims seen by estfstudio.
-- Run it after 11_publish.sql. Safe to run again: every statement is `if not exists`.
--
-- Each row is one sighting: the probe upload of a film's picture was blocked (claim_type 'visual' — the sample is
-- silent), or a film estfstudio had already uploaded was found blocked on a later look (the music had been swapped →
-- 'visual'; the picture had passed → 'audio'; neither known → null). YouTube's API only says that a video is blocked,
-- never why, so the type is inferred and `found_by` says which test saw it. The rows let you read the trend per source
-- account (`uploader`) or claimant — a studio claiming a whole series — without opening workspace/youtube_claims.json.
-- TEXT ONLY, an append-only log (estfstudio inserts, never updates).

create table if not exists youtube_claims (
  id text primary key,                          -- found_by || ':' || source id (or title) || ':' || claimed_at
  title text not null,                          -- the work's name
  claim_type text check (claim_type in ('visual', 'audio')),
  claimant text,                                -- who made the claim, when known (read by hand from YouTube Studio)
  uploader text,                                -- the source account the work came from
  source_id text,                               -- the source video's id (a Bilibili BV id)
  video_id text,                                -- the YouTube video it was seen on
  brand_id text references brands (id) on delete set null,
  found_by text not null default 'probe' check (found_by in ('probe', 'watch', 'manual')),
  detail text,
  claimed_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);
create index if not exists youtube_claims_recent on youtube_claims (claimed_at desc);
create index if not exists youtube_claims_uploader on youtube_claims (uploader, claim_type);

alter table youtube_claims enable row level security;   -- service-role only, like every table here
