"""SupabaseStore against a real PostgREST in front of the real schema (sql/*.sql).

Skipped unless FLASHTREND_TEST_REST_URL (a bare PostgREST, no /rest/v1) and FLASHTREND_TEST_JWT
(a service_role token) are set — see tests/integration/README.md. Never run against a real project.
"""
import dataclasses
import os
import unittest
from datetime import timedelta

from application.digest import RunDigest
from domain.models import Media, PreviousSnapshot
from tests.fakes import NOW, FakeChart, FakeEmbedder, FakeImageHost, FakeSource, FakeWriter


class PaddedEmbedder(FakeEmbedder):
    """The schema demands 384 dimensions; zero-padding keeps every cosine of the docs sample."""

    def encode(self, texts):
        return [v + [0.0] * (384 - len(v)) for v in super().encode(texts)]


REST = os.environ.get("FLASHTREND_TEST_REST_URL")
JWT = os.environ.get("FLASHTREND_TEST_JWT")


@unittest.skipUnless(REST and JWT, "needs FLASHTREND_TEST_REST_URL and FLASHTREND_TEST_JWT")
class SupabaseStoreIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from supabase import create_client

        from infrastructure.supabase_store import SupabaseStore

        client = create_client(REST, JWT)
        client.postgrest.base_url = client.postgrest.base_url.__class__(REST)  # bare PostgREST
        cls.store = SupabaseStore(client)

    def run_digest(self, clock_offset_h=0, **kw):
        now = NOW + timedelta(hours=clock_offset_h)
        return RunDigest(
            self.store, FakeSource(videos=[dataclasses.replace(v, captured_at=now) for v in
                                           FakeSource().videos]),
            PaddedEmbedder(), FakeWriter(), image_host=FakeImageHost(), chart=FakeChart(),
            clock=lambda: now, **kw,
        ).run()

    def test_01_config_round_trip(self):
        c = self.store.get_app_config()
        self.assertEqual((c.schema_version, c.z_threshold, c.relaxed_z_threshold, c.min_cohort_n),
                         (1, 1.5, 0.5, 20))
        self.assertIn("hoạt hình 3D trung quốc", c.keywords)
        self.assertEqual((len(c.keywords), c.regions), (7, ("VN",)))

    def test_02_full_run_writes_everything_the_docs_promise(self):
        r = self.run_digest()
        self.assertEqual((r.status, r.stats.ideas_count), ("ok", 2), r.error)
        db = self.store._db
        run = db.table("runs").select("*").eq("id", r.run_id).execute().data[0]
        self.assertEqual((run["status"], run["collected"], run["outliers"], run["ideas_count"], run["cohort_n"]),
                         ("ok", 5, 3, 2, 5))
        self.assertAlmostEqual(run["cohort_mu_ratio"], 18.7156, places=3)
        self.assertAlmostEqual(run["z_threshold_used"], 0.5)
        self.assertTrue(run["started_at"].endswith("+07:00"), run["started_at"])  # DB shows Vietnam time
        self.assertTrue(run["chart_media_id"].startswith("img_"))
        ideas = db.table("ideas").select("video_id,llm,status,duplicates_count").eq("run_id", r.run_id).execute().data
        self.assertEqual(sorted(i["video_id"] for i in ideas), ["yt_vid001", "yt_vid004"])
        self.assertTrue(all(i["llm"]["angles"] and i["status"] == "new" for i in ideas))
        cands = db.table("candidates").select("video_id,passed_z").eq("run_id", r.run_id).execute().data
        self.assertEqual(len(cands), 5)
        self.assertEqual(sum(c["passed_z"] for c in cands), 3)
        self.assertEqual(len(db.table("snapshots").select("video_id").eq("run_id", r.run_id).execute().data), 5)
        self.assertEqual(len(db.table("embeddings").select("video_id").execute().data), 3)

    def test_03_second_run_sees_history_velocity_and_keeps_status_and_first_seen(self):
        db = self.store._db
        first = db.table("videos").select("first_seen_at").eq("id", "yt_vid001").execute().data[0]["first_seen_at"]
        db.table("ideas").update({"status": "used"}).eq("video_id", "yt_vid001").execute()  # estfstudio's write
        r = self.run_digest(clock_offset_h=11)
        # vid001 was proposed in the last 90 days → not proposed again; vid004 likewise
        self.assertEqual((r.status, r.stats.ideas_count), ("ok", 0), r.error)
        v = db.table("videos").select("first_seen_at,last_run_id").eq("id", "yt_vid001").execute().data[0]
        self.assertEqual(v["first_seen_at"], first)
        self.assertEqual(v["last_run_id"], r.run_id)
        c = db.table("candidates").select("velocity,acceleration").eq("run_id", r.run_id).eq(
            "video_id", "yt_vid001").execute().data[0]
        self.assertIsNotNone(c["velocity"])  # a previous snapshot existed 11 h earlier
        self.assertIsNone(c["acceleration"])  # but only one
        status = db.table("ideas").select("status").eq("video_id", "yt_vid001").execute().data
        self.assertEqual([s["status"] for s in status], ["used"])  # never reset by the bot

    def test_04_embeddings_round_trip_and_history_cosine(self):
        got = self.store.get_embeddings(["yt_vid001"])["yt_vid001"][1]
        self.assertEqual(len(got), 384)
        self.assertAlmostEqual(self.store.nearest_history(got, 90, []), 1.0, places=5)
        self.assertLess(self.store.nearest_history(got, 90, ["yt_vid001"]), 1.0)
        self.assertIsNone(self.store.nearest_history(got, 90, ["yt_vid001", "yt_vid002", "yt_vid004"]))

    def test_05_media_reuse_and_alive_flag(self):
        m = Media("img_" + "ab" * 8, "estfstudio", "cover", "https://h/c.png", "nobinobi", "ab" * 32, 10)
        self.store.insert_media(m)
        self.assertEqual(self.store.find_media("ab" * 32).owner, "estfstudio")
        self.store.set_media_alive(m.id, False, NOW)
        row = self.store._db.table("media").select("alive,checked_at").eq("id", m.id).execute().data[0]
        self.assertFalse(row["alive"])
        self.assertIn(m.id, [x.id for x in self.store.list_media()])

    def test_06_cleanup_and_db_size(self):
        self.assertGreater(self.store.db_size_bytes(), 0)
        counts = self.store.cleanup(90, 90)
        self.assertEqual(set(counts), {"snapshots", "candidates", "embeddings", "videos"})

    def test_07_previous_snapshots_window_and_limit(self):
        prev = self.store.previous_snapshots(["yt_vid001"], NOW + timedelta(hours=12), 2)["yt_vid001"]
        self.assertEqual(len(prev), 2)
        self.assertGreater(prev[0].captured_at, prev[1].captured_at)  # newest first
        self.assertIsInstance(prev[0], PreviousSnapshot)


if __name__ == "__main__":
    unittest.main()
