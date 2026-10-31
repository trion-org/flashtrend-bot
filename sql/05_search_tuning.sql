-- Migration for a database that already ran 01_core.sql: two knobs for a niche feed.
-- (Fresh installs get these columns from 01_core.sql; `if not exists` makes this safe to run anyway.)
--   chart_enabled        false = skip the generic mostPopular chart, so the Z-Score cohort is only the niche
--   search_window_hours  how far back keyword search looks; a niche with few uploads needs days, not hours
-- After running this, run 04_seed_app_config.sql again to apply the values.
alter table app_config add column if not exists chart_enabled boolean not null default true;
alter table app_config add column if not exists search_window_hours int not null default 48
  check (search_window_hours between 1 and 4320);
