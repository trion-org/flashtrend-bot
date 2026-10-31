-- Seed (or re-seed) the single app_config row. Safe to run again: it updates the row in place.
-- Run 05_search_tuning.sql, 06_bilibili.sql and 07_analysis.sql first: they add the columns this row sets.
--
-- Niche: LONG COMPILATIONS of Chinese 3D animation and Chinese AI animation (donghua, AI manju): a whole season
-- or several series in one upload that runs for hours. Tuned against live results (2026-10-31):
--   * min_duration_sec 14400 (4 h) + niche_only: a video shorter than 4 h, or one that is not the niche, is dropped
--     before scoring. The platforms are asked for long videos too (Bilibili duration=4, YouTube videoDuration=long).
--     Probed on Bilibili: 8 compilation queries gave 61 distinct videos of 4 h or more (some 10 to 80 hours).
--   * niche_terms mark the niche by title/description; niche_exclude_terms drop courses and novel narration,
--     which also run for hours (AI-animation tutorials, 小说 audio). A title is checked for the exclusions only.
--   * compilations are months old, so the window is 90 days (2160 h) and decay_lambda 0.001 (a 7-day-old video
--     keeps 85% of its score, a 90-day-old one 12%); 0.01 would zero everything older than a week.
--   * on YouTube short, broad terms work and the length filter does the rest; phrases with 全集/合集 returned
--     nothing in a 7-day window. The generic chart stays off: it filled the cohort with off-topic music and esports.
--   * Bilibili is searched with its own Chinese list (bilibili_keywords): its search is full-text. 玄幻动画 and
--     国创 3D were blocked (HTTP 412) in a probe; the run skips a blocked keyword. Each keyword reads 2 pages.
--   * Bilibili's live "hot now" ranking of 国创 series (season_type 4) is listed too, under kind = 'series'.
--   * niche_boost 3 lifts the niche in the idea order and the hot list (viral_score itself is untouched).
-- Cron runs every hour, which changes three budgets, so:
--   * youtube_search_every_hours 6: 8 keywords x 100 units x 4 runs = 3,200 of the 10,000 daily quota
--     (hourly would be 19,200); the other hours read Bilibili only, which costs no quota
--   * analysis_every_hours 3: 8 charts per drawing hour go to the image host (64 a day, not 192)
--   * snapshot_ttl_days 14: hourly snapshots and candidates are ~24x a daily run's; 90 days would not fit 500 MB
-- Each YouTube keyword costs one search.list call (100 quota units per run): 8 keywords = 800 units.
-- A Bilibili keyword costs no quota (2 requests each, with a pause).
insert into app_config (
  keywords, bilibili_keywords, bilibili_series_types, niche_terms, niche_exclude_terms, niche_boost,
  niche_only, min_duration_sec, regions, llm_enabled, chart_enabled, search_window_hours, decay_lambda,
  youtube_search_every_hours, analysis_every_hours, snapshot_ttl_days
)
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
  array['国漫 合集', '3D国漫 全集 连播', '修仙动画 合集', '3D动画 合集 小时', '国漫 通宵 连播', '一口气看完 国漫',
        'AI漫剧 合集', '玄幻动漫 合集'],
  array[4],
  array['国漫', '国创', '动漫', '漫剧', '修仙', '玄幻', '仙侠', '3D动画', 'AI动画', 'donghua', 'xianxia',
        'Chinese animation', 'Chinese 3D', 'Chinese AI'],
  array['教程', '教学', '课程', '解说', '说书', 'tutorial'],
  3,
  true,
  14400,
  array['VN'],
  true,
  false,
  2160,
  0.001,
  6,
  3,
  14
)
on conflict (id) do update
  set keywords = excluded.keywords,
      bilibili_keywords = excluded.bilibili_keywords,
      regions = excluded.regions,
      llm_enabled = excluded.llm_enabled,
      chart_enabled = excluded.chart_enabled,
      search_window_hours = excluded.search_window_hours,
      decay_lambda = excluded.decay_lambda,
      bilibili_series_types = excluded.bilibili_series_types,
      niche_terms = excluded.niche_terms,
      niche_exclude_terms = excluded.niche_exclude_terms,
      niche_only = excluded.niche_only,
      min_duration_sec = excluded.min_duration_sec,
      niche_boost = excluded.niche_boost,
      youtube_search_every_hours = excluded.youtube_search_every_hours,
      analysis_every_hours = excluded.analysis_every_hours,
      snapshot_ttl_days = excluded.snapshot_ttl_days,
      updated_at = now();
