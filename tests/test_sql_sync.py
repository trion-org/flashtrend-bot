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
