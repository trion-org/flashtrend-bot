-- Seed the single app_config row. A second run fails on the primary key: use the UPDATE below.
insert into app_config (keywords, regions, llm_enabled)
values (array['python bot', 'ai tools', 'personal finance', 'street food', 'youtube shorts'],
        array['VN', 'JP'], true);

-- Re-seed when the row already exists:
-- update app_config
--   set keywords = array['python bot', 'ai tools', 'personal finance', 'street food', 'youtube shorts'],
--       regions = array['VN', 'JP'], llm_enabled = true, updated_at = now()
--   where id = 1;
