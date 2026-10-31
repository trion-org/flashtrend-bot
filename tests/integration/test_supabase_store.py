"""SupabaseStore against a real PostgREST in front of the real schema (sql/*.sql).

Skipped unless FLASHTREND_TEST_REST_URL (a bare PostgREST, no /rest/v1) and FLASHTREND_TEST_JWT
(a service_role token) are set — see tests/integration/README.md. Never run against a real project.
"""
import dataclasses
import os
import unittest
from datetime import timedelta

from application.digest import RunDigest
from domain.models import HotVideo, Media, PreviousSnapshot, RunRequest
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

    def run_digest(self, clock_offset_h=0, request=None, **kw):
        # the seed asks for 4 h compilations of the niche; the sample cohort is ten-minute YouTube videos
        self.store._db.table("app_config").update({"min_duration_sec": 0, "niche_only": False}).eq("id", 1).execute()
        now = NOW + timedelta(hours=clock_offset_h)
        return RunDigest(
            self.store, FakeSource(videos=[dataclasses.replace(v, captured_at=now) for v in
                                           FakeSource().videos]),
            PaddedEmbedder(), FakeWriter(), image_host=FakeImageHost(), chart=FakeChart(),
            clock=lambda: now, **kw,
        ).run(request)

    def test_01_config_round_trip(self):
        c = self.store.get_app_config()
        self.assertEqual((c.schema_version, c.z_threshold, c.relaxed_z_threshold, c.min_cohort_n),
                         (1, 1.5, 0.5, 20))
        self.assertIn("国漫", c.keywords)  # Chinese keywords survive the DB round trip
        self.assertIn("Chinese AI animation", c.keywords)
        self.assertEqual((len(c.keywords), c.regions), (8, ("VN",)))
        self.assertEqual((c.chart_enabled, c.search_window_hours, c.decay_lambda), (False, 2160, 0.001))
        self.assertEqual((c.min_duration_sec, c.niche_only, "教程" in c.niche_exclude_terms), (14400, True, True))
        self.assertEqual((c.bilibili_series_types, c.niche_boost, c.snapshot_ttl_days), ((4,), 3.0, 14))
        self.assertEqual((c.youtube_search_every_hours, c.analysis_every_hours), (6, 3))
        self.assertEqual(len(c.bilibili_keywords), 8)
        self.assertIn("国漫 合集", c.bilibili_keywords)

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
        card = db.table("media").select("kind,caption,position").eq("id", run["chart_media_id"]).execute().data[0]
        self.assertEqual(card, {"kind": "analysis", "caption": "Video đang hot", "position": 1})
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
        self.assertEqual(set(counts),
                         {"snapshots", "candidates", "embeddings", "videos", "hot_videos", "analysis_charts"})

    def test_07_previous_snapshots_window_and_limit(self):
        prev = self.store.previous_snapshots(["yt_vid001"], NOW + timedelta(hours=12), 2)["yt_vid001"]
        self.assertEqual(len(prev), 2)
        self.assertGreater(prev[0].captured_at, prev[1].captured_at)  # newest first
        self.assertIsInstance(prev[0], PreviousSnapshot)

    def test_08_hot_list_analysis_charts_run_history_and_their_cleanup(self):
        db = self.store._db
        r = self.run_digest(clock_offset_h=40)
        published = NOW - timedelta(hours=1)
        self.store.insert_hot_videos(r.run_id, [
            HotVideo("video", 1, "bi_BV1hot", "bilibili", "3D国漫 全集 <合集> & more", "https://www.bilibili.com/video/BV1hot",
                     "某UP主", 123456, 4342, published, True, 12.5),
            HotVideo("video", 2, "bi_BV2hot", "bilibili", "第二", "https://www.bilibili.com/video/BV2hot", None,
                     5, None, None, False, 3.25),
            HotVideo("series", 1, "bi_ss12548", "bilibili", "灵笼 第二季", "https://www.bilibili.com/bangumi/play/ss12548",
                     "9.8分 · 全12话", 402_207_839, None, None, True, 0.0),
        ])
        rows = db.table("hot_videos").select("*").eq("run_id", r.run_id).order("kind").order("rank").execute().data
        self.assertEqual([(h["kind"], h["rank"], h["niche"], h["views"], h["duration_sec"]) for h in rows],
                         [("series", 1, True, 402_207_839, None), ("video", 1, True, 123456, 4342),
                          ("video", 2, False, 5, None)])  # ranks restart per kind
        self.assertEqual(rows[1]["title"], "3D国漫 全集 <合集> & more")  # Chinese and markup survive untouched
        self.assertTrue(rows[1]["created_at"].endswith("+07:00"))

        chart = Media("img_" + "cd" * 8, "flashtrend", "analysis", "https://h/a.png", "nobinobi", "cd" * 32, 10,
                      run_id=r.run_id, caption="Phân bố z-score", position=3)
        self.store.insert_media(chart)
        got = db.table("media").select("kind,caption,position,run_id").eq("id", chart.id).execute().data[0]
        self.assertEqual(got, {"kind": "analysis", "caption": "Phân bố z-score", "position": 3, "run_id": r.run_id})

        history = self.store.recent_runs(50)
        self.assertEqual(history[-1].started_at.isoformat()[:13], (NOW + timedelta(hours=40)).isoformat()[:13])
        self.assertEqual([p.started_at for p in history], sorted(p.started_at for p in history))  # oldest first
        self.assertEqual(len(self.store.recent_runs(2)), 2)

        # cleanup drops expired hot lists and analysis charts, keeps fresh ones, and leaves other kinds alone
        db.table("hot_videos").update({"created_at": "2020-01-01T00:00:00+07:00"}).eq("kind", "video").eq("rank", 2).execute()
        db.table("media").update({"created_at": "2020-01-01T00:00:00+07:00"}).eq("id", chart.id).execute()
        counts = self.store.cleanup(14, 90)
        self.assertGreaterEqual(counts["hot_videos"], 1)
        self.assertGreaterEqual(counts["analysis_charts"], 1)
        left = db.table("hot_videos").select("kind,rank").eq("run_id", r.run_id).order("kind").execute().data
        self.assertEqual([(h["kind"], h["rank"]) for h in left], [("series", 1), ("video", 1)])
        self.assertEqual(db.table("media").select("id").eq("id", chart.id).execute().data, [])
        self.assertEqual(len(db.table("media").select("id").eq("id", "img_" + "ab" * 8).execute().data), 1)

    def test_09_title_translations_round_trip_and_ride_on_the_hot_list(self):
        self.store.upsert_titles_vi([("sha256:aa", "凡人修仙传", "Phàm Nhân Tu Tiên"), ("sha256:bb", "灵笼", "Linh Lung")])
        self.store.upsert_titles_vi([("sha256:aa", "凡人修仙传", "Phàm Nhân Tu Tiên (mới)")])  # same title: replaced
        self.assertEqual(self.store.get_titles_vi(["sha256:aa", "sha256:bb", "sha256:zz"]),
                         {"sha256:aa": "Phàm Nhân Tu Tiên (mới)", "sha256:bb": "Linh Lung"})
        r = self.run_digest(clock_offset_h=41)
        self.store.insert_hot_videos(r.run_id, [
            HotVideo("series", 1, "bi_ss1", "bilibili", "灵笼", "https://www.bilibili.com/bangumi/play/ss1", None,
                     9, None, None, True, 0.0, title_vi="Linh Lung"),
            HotVideo("series", 2, "bi_ss2", "bilibili", "牧神记", "https://www.bilibili.com/bangumi/play/ss2", None,
                     8, None, None, True, 0.0),
        ])
        rows = self.store._db.table("hot_videos").select("rank,title_vi").eq("run_id", r.run_id).order("rank").execute()
        self.assertEqual(rows.data, [{"rank": 1, "title_vi": "Linh Lung"}, {"rank": 2, "title_vi": None}])

    def test_10_a_one_off_look_keeps_its_request_and_stays_off_the_timeline(self):
        before = len(self.store.recent_runs(500))
        request = RunRequest("search", "phim hoạt hình Tây Du Ký", "tg1x42")
        r = self.run_digest(clock_offset_h=42, request=request)
        self.assertEqual(r.run_id[-7:], "_search")
        row = self.store._db.table("runs").select("mode,query,query_zh,request_id,status").eq("id", r.run_id)
        self.assertEqual(row.execute().data, [{"mode": "search", "query": "phim hoạt hình Tây Du Ký",
                                               "query_zh": None, "request_id": "tg1x42", "status": "ok"}])
        self.assertEqual(len(self.store.recent_runs(500)), before)  # the timeline counts digest runs only
        digest = self.store._db.table("runs").select("mode").neq("id", r.run_id).limit(1).execute().data
        self.assertEqual(digest, [{"mode": "digest"}])  # rows written without a request keep the default


if __name__ == "__main__":
    unittest.main()
