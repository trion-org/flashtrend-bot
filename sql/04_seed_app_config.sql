-- Seed (or re-seed) the single app_config row. Safe to run again: it updates the row in place.
-- Run 05_search_tuning.sql first on a database created before it existed.
--
-- Niche: Chinese 3D animation and Chinese AI animation (donghua, AI manju), often multi-episode uploads that
-- run for hours. Tuned against live YouTube results (2026-10-31):
--   * short, broad Chinese terms work; phrases with 全集/合集 or "国创 3D" return nothing (treated as AND)
--   * "3D动画" alone returns unrelated viral clips, so "3D" cannot be searched on its own
--   * a 48 h window left most keywords empty; 168 h (7 days) gives each keyword ~25 videos
--   * the generic chart is switched off: it filled the cohort (and the digest) with off-topic music and esports
--   * decay_lambda 0.01 (half-life ~69 h) instead of 0.05 (~14 h): with a 7-day window 0.05 would zero every score
-- Each keyword costs one search.list call (100 YouTube quota units per run): 8 keywords = 800 units.
insert into app_config (keywords, regions, llm_enabled, chart_enabled, search_window_hours, decay_lambda)
values (
  array[
    '国漫',
    '修仙动画',
    '玄幻动画',
    'AI漫剧',
    'AI动画',
    'Chinese animation full episodes',
    'Chinese AI animation',
    'Chinese 3D animation full episodes'
  ],
  array['VN'],
  true,
  false,
  168,
  0.01
)
on conflict (id) do update
  set keywords = excluded.keywords,
      regions = excluded.regions,
      llm_enabled = excluded.llm_enabled,
      chart_enabled = excluded.chart_enabled,
      search_window_hours = excluded.search_window_hours,
      decay_lambda = excluded.decay_lambda,
      updated_at = now();
