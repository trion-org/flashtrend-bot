-- Seed (or re-seed) the single app_config row. Safe to run again: it updates the row in place.
-- Niche: Chinese 3D animation and Chinese AI animation (donghua), often multi-episode uploads that run
-- for hours. Keywords are searched in Chinese and English. Each keyword costs one search.list call
-- (100 YouTube quota units per run), so keep the list short: 8 keywords = 800 units per run.
insert into app_config (keywords, regions, llm_enabled)
values (
  array[
    '国漫 3D动画 全集',
    '3D玄幻动画 合集',
    '修仙 3D动画 全集',
    'AI动画 国产 全集',
    'AI漫剧 合集',
    'Chinese 3D animation full episodes',
    'Chinese AI animation',
    'donghua 3D eng sub full'
  ],
  array['VN'],
  true
)
on conflict (id) do update
  set keywords = excluded.keywords,
      regions = excluded.regions,
      llm_enabled = excluded.llm_enabled,
      updated_at = now();
