-- Seed (or re-seed) the single app_config row. Safe to run again: it updates the row in place.
-- Niche: Chinese 3D animation and Chinese AI animation (donghua), often multi-episode uploads that run
-- for hours. Each keyword costs one search.list call (100 YouTube quota units per run), so keep the list short.
insert into app_config (keywords, regions, llm_enabled)
values (
  array[
    'hoạt hình 3D trung quốc',
    'phim hoạt hình 3D trung quốc vietsub',
    'hoạt hình AI trung quốc',
    'phim AI hoạt hình full tập',
    'donghua 3D vietsub',
    'tiên hiệp hoạt hình 3D',
    'hoạt hình 3D tổng hợp nhiều tập'
  ],
  array['VN'],
  true
)
on conflict (id) do update
  set keywords = excluded.keywords,
      regions = excluded.regions,
      llm_enabled = excluded.llm_enabled,
      updated_at = now();
