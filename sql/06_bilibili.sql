-- Migration for a database that already ran 01_core.sql: a separate keyword list for Bilibili.
-- (Fresh installs get the column from 01_core.sql; `if not exists` makes this safe to run anyway.)
--   bilibili_keywords  Chinese search terms for Bilibili; an empty list turns Bilibili off
-- After running this, run 04_seed_app_config.sql again to apply the values.
alter table app_config add column if not exists bilibili_keywords text[] not null default '{}';
