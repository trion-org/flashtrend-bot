-- Migration 09 — one-off looks: Bilibili's hot lists (trending) or one search, beside the hourly digest.
-- Run it on EVERY database (fresh or old) after 08_titles_vi.sql.
-- Safe to run again: every statement is `if not exists`.
--
-- runs.mode says what a run looked for; a one-off run also keeps its query, the query in Chinese (what was
-- searched on Bilibili) and the caller's tag (estfstudio's /analysis finds its run by it).

alter table runs add column if not exists mode text not null default 'digest'
  check (mode in ('digest', 'trending', 'search'));
alter table runs add column if not exists query text;        -- search: as typed (any language)
alter table runs add column if not exists query_zh text;     -- search: what was searched; null = as typed
alter table runs add column if not exists request_id text;   -- the caller's tag
create index if not exists runs_request_id on runs (request_id) where request_id is not null;
