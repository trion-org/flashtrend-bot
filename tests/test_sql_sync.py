"""sql/*.sql is generated from the DDL blocks of the design docs: the two must not drift apart."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def doc_blocks(name: str) -> dict[str, str]:
    src = (ROOT / "tools/docs" / name).read_text(encoding="utf-8")
    return dict(re.findall(r'```sql title="([^"]+)"\n(.*?)\n```', src, flags=re.S))


class SqlSyncTest(unittest.TestCase):
    def test_core_and_media_ddl_match_the_docs(self):
        blocks = doc_blocks("03-du-lieu.archify.md")
        core = next(v for k, v in blocks.items() if k.startswith("Schema v1"))
        proposed = next(v for k, v in blocks.items() if k.startswith("Cột đề xuất"))
        media = next(v for k, v in blocks.items() if k.startswith("media"))
        self.assertIn(core, (ROOT / "sql/01_core.sql").read_text(encoding="utf-8"))
        self.assertIn(proposed, (ROOT / "sql/01_core.sql").read_text(encoding="utf-8"))
        self.assertIn(media, (ROOT / "sql/02_media.sql").read_text(encoding="utf-8"))

    def test_migration_adds_exactly_the_columns_a_fresh_install_has(self):
        core = (ROOT / "sql/01_core.sql").read_text(encoding="utf-8")
        migration = (ROOT / "sql/05_search_tuning.sql").read_text(encoding="utf-8")
        for column in ("chart_enabled", "search_window_hours"):
            self.assertIn(f"add column {column}", core)
            self.assertIn(f"add column if not exists {column}", migration)

    def test_bilibili_column_is_in_both_the_fresh_schema_and_the_migration(self):
        core = (ROOT / "sql/01_core.sql").read_text(encoding="utf-8")
        migration = (ROOT / "sql/06_bilibili.sql").read_text(encoding="utf-8")
        self.assertIn("add column bilibili_keywords text[]", core)
        self.assertIn("add column if not exists bilibili_keywords text[]", migration)

    def test_seed_sets_every_niche_knob(self):
        seed = (ROOT / "sql/04_seed_app_config.sql").read_text(encoding="utf-8")
        for field in ("keywords", "bilibili_keywords", "bilibili_series_types", "niche_terms", "niche_boost",
                      "chart_enabled", "search_window_hours", "decay_lambda", "youtube_search_every_hours",
                      "analysis_every_hours", "snapshot_ttl_days", "niche_exclude_terms", "niche_only",
                      "min_duration_sec"):
            self.assertRegex(seed, rf"{field} = excluded\.{field}")

    def test_migration_07_is_the_docs_block_and_adds_every_new_column(self):
        block = next(v for k, v in doc_blocks("06-bang-mo-rong.archify.md").items() if k.startswith("Migration 07"))
        migration = (ROOT / "sql/07_analysis.sql").read_text(encoding="utf-8")
        self.assertIn(block, migration)
        for column in ("caption", "position", "bilibili_series_types", "niche_terms", "niche_boost",
                       "youtube_search_every_hours", "analysis_every_hours", "niche_exclude_terms", "niche_only",
                       "min_duration_sec"):
            self.assertRegex(migration, rf"add column if not exists {column} ")
        self.assertIn("create table if not exists hot_videos", migration)
        self.assertIn("alter table hot_videos enable row level security", migration)
        self.assertNotIn("create policy", migration)

    def test_migration_08_is_the_docs_block(self):
        block = next(v for k, v in doc_blocks("06-bang-mo-rong.archify.md").items() if k.startswith("Migration 08"))
        migration = (ROOT / "sql/08_titles_vi.sql").read_text(encoding="utf-8")
        self.assertIn(block, migration)
        self.assertIn("alter table titles_vi enable row level security", migration)
        self.assertRegex(migration, r"alter table hot_videos add column if not exists title_vi ")

    def test_migration_09_is_the_docs_block_and_adds_the_run_modes(self):
        block = next(v for k, v in doc_blocks("06-bang-mo-rong.archify.md").items() if k.startswith("Migration 09"))
        migration = (ROOT / "sql/09_run_modes.sql").read_text(encoding="utf-8")
        self.assertIn(block, migration)
        for column in ("mode", "query", "query_zh", "request_id"):
            self.assertRegex(migration, rf"alter table runs add column if not exists {column} ")
        self.assertIn("check (mode in ('digest', 'trending', 'search'))", migration)

    def test_cleanup_is_safe_on_a_database_without_migration_07(self):
        sql = (ROOT / "sql/03_functions.sql").read_text(encoding="utf-8")
        self.assertIn("exception when undefined_table", sql)  # no hot_videos table yet
        self.assertIn("kind::text = 'analysis'", sql)  # no enum value yet: compare as text

    def test_database_is_set_to_vietnam_time(self):
        sql = (ROOT / "sql/01_core.sql").read_text(encoding="utf-8")
        self.assertIn("set timezone to 'Asia/Ho_Chi_Minh'", sql)

    def test_functions_are_locked_to_service_role(self):
        sql = (ROOT / "sql/03_functions.sql").read_text(encoding="utf-8")
        for fn in ("flashtrend_max_cosine", "flashtrend_cleanup", "flashtrend_db_size"):
            self.assertRegex(sql, rf"revoke execute on function {fn}\(.*\) from public, anon, authenticated")
            self.assertRegex(sql, rf"grant execute on function {fn}\(.*\) to service_role")

    def test_every_table_has_rls_and_no_anon_policy(self):
        sql = (ROOT / "sql/01_core.sql").read_text(encoding="utf-8") + (ROOT / "sql/02_media.sql").read_text(
            encoding="utf-8")
        tables = re.findall(r"^create table (\w+)", sql, flags=re.M)
        self.assertEqual(len(tables), 11)  # 10 core tables + media
        for t in tables:
            self.assertIn(f"alter table {t} enable row level security", sql, t)
        self.assertNotIn("create policy", sql)


if __name__ == "__main__":
    unittest.main()
