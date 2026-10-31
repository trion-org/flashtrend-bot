import dataclasses
import unittest
from datetime import timedelta

from application.digest import RunDigest
from domain import errors as E
from domain.errors import FlashTrendError
from domain.models import QUERY_MAX_CHARS, AppConfig, HotSeries, PreviousSnapshot, RunRequest
from tests.fakes import (
    NOW,
    FakeChart,
    FakeEmbedder,
    FakeImageHost,
    FakeSource,
    FakeStore,
    FakeWriter,
    good_llm,
    sample_channels,
    sample_videos,
)

RUN_ID = "run_20261028T071712"


class Obs:
    def __init__(self):
        self.lines: list[str] = []

    def info(self, m):
        self.lines.append(m)

    warn = info


def make(store=None, source=None, writer="default", host=None, chart=True, analysis=None, **kw):
    store = store or FakeStore()
    writer = FakeWriter() if writer == "default" else writer
    obs = Obs()
    uc = RunDigest(
        store, source or FakeSource(), FakeEmbedder(), writer,
        image_host=host, chart=FakeChart() if chart else None, analysis=analysis,
        observer=obs, clock=lambda: NOW, sleep=lambda s: None, **kw,
    )
    return uc, store, obs


class HappyPathTest(unittest.TestCase):
    def setUp(self):
        self.host = FakeImageHost()
        self.uc, self.store, self.obs = make(host=self.host)
        self.result = self.uc.run()

    def test_run_ok_with_docs_sample_numbers(self):
        r = self.result
        self.assertEqual((r.run_id, r.status, r.error), (RUN_ID, "ok", None))
        s = r.stats
        self.assertEqual((s.collected, s.scored, s.outliers, s.ideas_count), (5, 5, 3, 2))
        self.assertEqual(s.cohort.n, 5)
        self.assertAlmostEqual(s.cohort.mu_ratio, 18.7156, places=3)
        self.assertAlmostEqual(s.cohort.sigma_ratio, 16.2272, places=3)
        self.assertAlmostEqual(s.cohort.median_engagement, 0.0938, places=4)
        self.assertEqual(s.cohort.z_threshold_used, 0.5)  # 5 < min_cohort_n → relaxed

    def test_closed_run_row(self):
        row = self.store.runs[RUN_ID]
        self.assertEqual((row["status"], row["error"], row["region"]), ("ok", None, "VN"))
        self.assertIsNotNone(row["stats"].duration_ms)
        self.assertEqual(self.store.cleaned, (90, 90))

    def test_candidates_cover_every_video_and_flag_outliers(self):
        by_id = {c.video.native_id: c for c in self.store.candidates}
        self.assertEqual(len(by_id), 5)
        passed = {k for k, c in by_id.items() if c.passed_z}
        self.assertEqual(passed, {"vid001", "vid002", "vid004"})
        self.assertAlmostEqual(by_id["vid001"].viral_score, 27.49, delta=0.02)
        self.assertAlmostEqual(by_id["vid004"].viral_score, 17.39, delta=0.02)

    def test_two_leaders_vid001_absorbs_vid002(self):
        ideas = {i.candidate.video.native_id: i for i in self.result.ideas}
        self.assertEqual(set(ideas), {"vid001", "vid004"})
        self.assertEqual(ideas["vid001"].duplicates_count, 1)
        self.assertEqual(ideas["vid004"].duplicates_count, 0)
        self.assertEqual(ideas["vid001"].cluster_id, f"{RUN_ID}_c0")
        self.assertEqual(ideas["vid001"].channel_title, "Python Lab VN")
        self.assertEqual(ideas["vid001"].novelty_score, 1.0)

    def test_every_idea_has_a_valid_llm_and_it_was_stored(self):
        for idea in self.store.ideas.values():
            self.assertEqual(len(idea.llm["angles"]), 3)

    def test_snapshots_and_videos_written_for_all(self):
        self.assertEqual(len(self.store.videos), 5)
        self.assertEqual(len(self.store.snapshots), 5)
        self.assertEqual({t for _, t, _ in self.store.snapshots}, {90})

    def test_only_outliers_are_embedded(self):
        self.assertEqual(set(self.store.embeddings), {"yt_vid001", "yt_vid002", "yt_vid004"})

    def test_history_search_excludes_this_runs_outliers(self):
        self.assertEqual(sorted(self.store.nearest_calls[0]), ["yt_vid001", "yt_vid002", "yt_vid004"])

    def test_chart_uploaded_once_and_linked(self):
        self.assertEqual(self.host.uploads, [f"{RUN_ID}_top.png"])
        media_id = self.store.runs[RUN_ID]["chart_media_id"]
        m = self.store.media[media_id]
        self.assertEqual((m.owner, m.kind, m.run_id), ("flashtrend", "analysis", RUN_ID))
        self.assertEqual((m.caption, m.position), ("Video đang hot", 1))
        self.assertTrue(media_id.startswith("img_") and len(media_id) == 20)

    def test_no_thumbnail_is_uploaded(self):
        self.assertEqual({m.kind for m in self.store.media.values()}, {"analysis"})


class FailureTest(unittest.TestCase):
    def test_schema_mismatch_stops_before_any_write(self):
        store = FakeStore(dataclasses.replace(AppConfig(keywords=("k",)), schema_version=2))
        uc, store, _ = make(store=store)
        with self.assertRaises(FlashTrendError) as cm:
            uc.run()
        self.assertEqual(cm.exception.code, E.SCHEMA_MISMATCH)
        self.assertEqual(store.runs, {})

    def test_youtube_quota_closes_run_as_error(self):
        err = FlashTrendError(E.YT_QUOTA, "quota", {"reason": "quotaExceeded"})
        uc, store, _ = make(source=FakeSource(error=err))
        r = uc.run()
        self.assertEqual(r.status, "error")
        self.assertEqual(r.error["code"], "YT_QUOTA")
        self.assertEqual(r.error["trace_id"], RUN_ID)
        self.assertEqual(set(r.error), {"code", "message", "details", "trace_id"})
        self.assertEqual(store.runs[RUN_ID]["status"], "error")
        self.assertEqual((r.stats.collected, r.stats.ideas_count), (0, 0))

    def test_unexpected_exception_is_wrapped_and_run_closed(self):
        uc, store, _ = make(source=FakeSource(error=KeyError("boom")))
        r = uc.run()
        self.assertEqual(r.error["code"], E.UNEXPECTED)
        self.assertEqual(store.runs[RUN_ID]["status"], "error")

    def test_gemini_bad_schema_twice_keeps_l1_l2_with_null_llm(self):
        writer = FakeWriter(outputs=[{"summary": "x"}, {"summary": "x"}])
        uc, store, _ = make(writer=writer)
        r = uc.run()
        self.assertEqual((r.status, r.error["code"]), ("error", E.GEMINI_SCHEMA))
        self.assertEqual(len(store.candidates), 5)
        self.assertEqual(len(store.ideas), 2)
        self.assertTrue(all(i.llm is None for i in store.ideas.values()))
        self.assertEqual(r.stats.ideas_count, 2)
        self.assertIsNone(store.cleaned)  # housekeeping only after a good run

    def test_gemini_bad_schema_once_is_retried(self):
        writer = FakeWriter(outputs=[{"summary": "x"}, good_llm(), good_llm(format="long")])
        uc, store, _ = make(writer=writer)
        r = uc.run()
        self.assertEqual(r.status, "ok")
        self.assertEqual(len(writer.briefs), 3)

    def test_gemini_rate_limit_marks_error(self):
        writer = FakeWriter(error=FlashTrendError(E.GEMINI_RATE_LIMIT, "429"))
        uc, store, _ = make(writer=writer)
        r = uc.run()
        self.assertEqual(r.error["code"], E.GEMINI_RATE_LIMIT)
        self.assertEqual(len(store.ideas), 2)

    def test_llm_disabled_keeps_ideas_but_never_ok(self):
        store = FakeStore(AppConfig(keywords=("k",), llm_enabled=False))
        writer = FakeWriter()
        uc, store, _ = make(store=store, writer=writer)
        r = uc.run()
        self.assertEqual((r.status, r.error["code"]), ("error", E.LLM_DISABLED))
        self.assertEqual(writer.briefs, [])
        self.assertEqual(len(store.ideas), 2)

    def test_image_failure_never_fails_the_run(self):
        uc, store, obs = make(host=FakeImageHost(fail=True))
        r = uc.run()
        self.assertEqual(r.status, "ok")
        self.assertIsNone(store.runs[RUN_ID]["chart_media_id"])
        self.assertTrue(any("top chart skipped" in line for line in obs.lines))

    def test_same_chart_sha_reuses_the_media_row(self):
        host = FakeImageHost()
        uc, store, _ = make(host=host)
        uc.run()
        first = dict(store.media)
        uc2, _, _ = make(store=store, host=host)
        uc2.run()  # same clock → same run id → same png bytes
        self.assertEqual(len(host.uploads), 1)
        self.assertEqual(store.media, first)

    def test_chart_skipped_without_host(self):
        uc, store, _ = make(host=None)
        self.assertEqual(uc.run().status, "ok")
        self.assertEqual(store.media, {})


class FakeAnalysis:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def render(self, run_id, now, candidates, ideas, history, growth=None):
        from application.ports import AnalysisImage

        self.calls.append((len(candidates), len(history)))
        self.history, self.growth = history, growth
        if self.error:
            raise self.error
        return [AnalysisImage(f"c{n}", f"Biểu đồ {n}", n, b"\x89PNG-%d" % n, 10, 5) for n in (2, 3)]


class AnalysisChartsTest(unittest.TestCase):
    def test_every_chart_becomes_an_analysis_media_row_with_caption_and_position(self):
        analysis, host = FakeAnalysis(), FakeImageHost()
        uc, store, _ = make(host=host, analysis=analysis)
        uc.run()
        rows = sorted(store.media.values(), key=lambda m: m.position)
        self.assertEqual([(m.kind, m.position, m.caption) for m in rows],
                         [("analysis", 1, "Video đang hot"), ("analysis", 2, "Biểu đồ 2"), ("analysis", 3, "Biểu đồ 3")])
        self.assertTrue(all(m.run_id == RUN_ID and m.owner == "flashtrend" for m in rows))
        self.assertEqual(analysis.calls, [(5, 1)])  # all scored candidates; no stored run yet, only this one

    def test_the_timeline_gets_the_stored_run_history(self):
        from application.ports import RunPoint

        store = FakeStore()
        store.history = [RunPoint(NOW - timedelta(hours=h), 100, 5, 1) for h in (3, 2, 1)]
        analysis = FakeAnalysis()
        uc = make(store=store, host=FakeImageHost(), analysis=analysis)[0]
        uc.run()
        self.assertEqual(analysis.calls[0][1], 4)  # the stored runs, then this one
        self.assertEqual(analysis.history[-1].collected, len(store.snapshots))  # counted like the stored ones

    def test_the_growth_chart_gets_the_hot_videos_earlier_snapshots(self):
        store, analysis = FakeStore(), FakeAnalysis()
        uc, _, _ = make(store=store, host=FakeImageHost(), analysis=analysis)
        uc.run()
        passed = {c.video.id for c in store.candidates if c.passed_z}
        self.assertTrue(passed)
        self.assertEqual(set(analysis.growth), passed)  # only the hot videos are looked up

    def test_a_crashing_renderer_only_loses_the_charts(self):
        uc, store, obs = make(host=FakeImageHost(), analysis=FakeAnalysis(RuntimeError("matplotlib")))
        self.assertEqual(uc.run().status, "ok")
        self.assertEqual([m.position for m in store.media.values()], [1])  # the card still went out
        self.assertTrue(any("analysis charts skipped" in line for line in obs.lines))

    def test_a_scheduled_run_draws_only_on_the_configured_hours(self):
        # NOW is 07:17 — 7 is not a multiple of 4, so the hourly cron skips the charts …
        store = FakeStore(AppConfig(analysis_every_hours=4))
        analysis, host = FakeAnalysis(), FakeImageHost()
        make(store=store, host=host, analysis=analysis, trigger="schedule")[0].run()
        self.assertEqual((analysis.calls, host.uploads, store.media), ([], [], {}))
        # … a manual run always draws, and so does an hour that divides evenly
        make(store=FakeStore(AppConfig(analysis_every_hours=4)), host=FakeImageHost(), analysis=analysis)[0].run()
        make(store=FakeStore(AppConfig(analysis_every_hours=7)), host=FakeImageHost(), analysis=analysis,
             trigger="schedule")[0].run()
        self.assertEqual(len(analysis.calls), 2)


class FakeTranslator:
    def __init__(self, error=None, chinese="西游记 动画"):
        self.error, self.asked, self.chinese, self.queries = error, [], chinese, []

    def translate(self, titles):
        self.asked.append(list(titles))
        if self.error:
            raise self.error
        return [f"VI {t}" for t in titles]

    def to_chinese(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.chinese


def bilibili_source():
    """The sample cohort as Bilibili videos: ten-minute clips, none of them in the niche."""
    return FakeSource(videos=[dataclasses.replace(v, id="bi_" + v.native_id, platform="bilibili",
                                                  url=f"https://www.bilibili.com/video/{v.native_id}")
                              for v in sample_videos()])


class RunModesTest(unittest.TestCase):
    NICHE = AppConfig(keywords=("python bot",), bilibili_keywords=("国漫 合集",), min_duration_sec=4 * 3600,
                      niche_only=True, niche_terms=("国漫",), niche_boost=3.0, bilibili_series_types=(4,))

    def run_mode(self, request, translator=None, analysis=None):
        source = bilibili_source()
        uc, store, obs = make(store=FakeStore(self.NICHE), source=source, translator=translator,
                              analysis=analysis, host=FakeImageHost() if analysis else None)
        return uc.run(request), store, source, obs

    def test_a_search_is_translated_searched_on_bilibili_alone_and_keeps_every_length(self):
        translator = FakeTranslator()
        request = RunRequest("search", "  phim hoạt hình   Tây Du Ký ", "tg1x2")
        result, store, source, obs = self.run_mode(request, translator)
        self.assertEqual((result.status, result.run_id), ("ok", RUN_ID + "_search"))
        self.assertEqual(translator.queries, ["phim hoạt hình Tây Du Ký"])
        self.assertEqual(source.searched, ("西游记 动画", self.NICHE.search_window_hours))
        self.assertFalse(hasattr(source, "collect_args"))  # no YouTube, no niche keywords
        self.assertEqual(source.series_args, ())  # no 国创 series either
        run = store.runs[result.run_id]
        self.assertEqual((run["request"], run["query_zh"]), (request, "西游记 动画"))
        rows = store.hot_videos[result.run_id]
        self.assertTrue(rows and all(r.duration_sec == 600 and not r.niche for r in rows))  # short, off-niche: kept
        self.assertEqual(store.ideas, {})  # a look, not an idea run: no embeddings, no Gemini ideas
        self.assertTrue(any("search 'phim hoạt hình Tây Du Ký' → '西游记 动画'" in line for line in obs.lines))

    def test_trending_reads_the_hot_lists_and_draws_no_timeline(self):
        analysis = FakeAnalysis()
        result, store, source, _ = self.run_mode(RunRequest("trending", "ignored", "tg9"), FakeTranslator(),
                                                 analysis)
        self.assertEqual((result.status, result.run_id), ("ok", RUN_ID + "_trending"))
        self.assertTrue(source.trended)
        self.assertIsNone(store.runs[result.run_id]["request"].query)  # only a search keeps a query
        self.assertEqual(analysis.history, [])  # the timeline is the hourly runs': not this look's

    def test_a_failed_translation_searches_what_was_typed(self):
        result, store, source, obs = self.run_mode(RunRequest("search", "西游记"), FakeTranslator(RuntimeError("429")))
        self.assertEqual(result.status, "ok")
        self.assertEqual(source.searched[0], "西游记")
        self.assertIsNone(store.runs[result.run_id]["query_zh"])
        self.assertTrue(any("search not translated to Chinese" in line for line in obs.lines))

    def test_the_hourly_digest_is_unchanged(self):
        result, store, source, _ = self.run_mode(None, FakeTranslator())
        self.assertEqual(result.run_id, RUN_ID)
        self.assertEqual(source.collect_args[1], ("python bot",))
        self.assertEqual(source.bilibili_keywords, ("国漫 合集",))
        self.assertIsNone(store.runs[RUN_ID]["request"])
        self.assertEqual(store.hot_videos.get(RUN_ID, []), [])  # ten-minute clips: below the 4 h minimum

    def test_a_request_is_checked(self):
        self.assertEqual(RunRequest("search", " a  b ").query, "a b")
        self.assertEqual(len(RunRequest("search", "x" * 500).query), QUERY_MAX_CHARS)
        self.assertEqual((RunRequest("digest", "x", "").query, RunRequest("digest", "x", "").request_id),
                         (None, None))
        self.assertFalse(RunRequest().ad_hoc)
        for bad in (("nope",), ("search", "  "), ("trending", None, "has space"), ("trending", None, "x" * 65)):
            with self.assertRaises(ValueError):
                RunRequest(*bad)


class TitleTranslationTest(unittest.TestCase):
    def test_the_hot_list_card_and_hot_videos_carry_their_titles_in_vietnamese_translated_once(self):
        store, translator = FakeStore(), FakeTranslator()
        make(store=store, translator=translator)[0].run()
        self.assertEqual(len(translator.asked), 1)  # one request for the whole run
        hot = [c for c in store.candidates if c.passed_z]
        self.assertTrue(hot and all(c.title_vi == f"VI {c.video.title}" for c in hot))
        self.assertEqual(hot[0].shown_title, f"VI {hot[0].video.title}")
        rows = [r for rows in store.hot_videos.values() for r in rows]
        self.assertTrue(all(r.title_vi == f"VI {r.title}" for r in rows))
        again = FakeTranslator()
        make(store=store, translator=again)[0].run()
        self.assertEqual(again.asked, [])  # every title already stored

    def test_a_failing_translator_leaves_the_original_titles(self):
        store = FakeStore()
        uc, _, obs = make(store=store, translator=FakeTranslator(RuntimeError("quota")))
        self.assertEqual(uc.run().status, "ok")
        self.assertTrue(all(c.title_vi is None and c.shown_title == c.video.title for c in store.candidates))
        self.assertTrue(any("titles not translated" in line for line in obs.lines))

    def test_without_a_translator_nothing_is_asked(self):
        store = FakeStore()
        make(store=store)[0].run()
        self.assertFalse(getattr(store, "titles_vi", {}))


class HotListTest(unittest.TestCase):
    @staticmethod
    def bilibili_pair(n=12):
        from domain.models import Channel, VideoSnapshot

        videos, channels = [], []
        for i in range(n):
            videos.append(VideoSnapshot(
                id=f"bi_BV{i}", platform="bilibili", native_id=f"BV{i}", url=f"https://www.bilibili.com/video/BV{i}",
                title=f"3D国漫 第{i}集" if i % 2 else f"旅行 vlog {i}", description="", published_at=NOW - timedelta(hours=5),
                channel_id=f"bi_{i}", duration_sec=3600, thumbnail_url=None, views=50_000 * (i + 1), likes=100,
                comments=10, captured_at=NOW, query_tag="k"))
            channels.append(Channel(id=f"bi_{i}", platform="bilibili", native_id=str(i), title=f"up{i}",
                                    subscriber_count=1000, video_count=5, channel_avg_views=1000.0,
                                    fetched_at=NOW, stale_after=NOW + timedelta(hours=24)))
        return videos, channels

    def run_with(self, config, source=None, **kw):
        more, more_ch = self.bilibili_pair()
        if source is None:
            source = FakeSource()
        source.videos = source.videos + more
        source.channels.update({c.id: c for c in more_ch})
        store = FakeStore(config)
        uc, store, obs = make(store=store, source=source, **kw)
        uc.run()
        return store, obs

    def test_only_bilibili_goes_to_the_hot_list_at_most_ten_in_rank_order(self):
        store, _ = self.run_with(AppConfig())
        rows = store.hot_videos[RUN_ID]
        self.assertEqual([h.rank for h in rows], list(range(1, 11)))
        self.assertTrue(all(h.platform == "bilibili" for h in rows))
        scores = [h.viral_score for h in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_a_checked_video_carries_the_total_its_part_count_and_part_one(self):
        source = FakeSource()
        source.parts = {"bi_BV11": [420, 34260], "bi_BV9": [7200]}
        store, _ = self.run_with(AppConfig(), source=source)
        rows = {h.video_id: h for h in store.hot_videos[RUN_ID]}
        self.assertEqual((rows["bi_BV11"].duration_sec, rows["bi_BV11"].parts, rows["bi_BV11"].first_part_sec),
                         (34680, 2, 420))
        self.assertEqual((rows["bi_BV9"].parts, rows["bi_BV9"].first_part_sec), (1, 7200))
        self.assertIsNone(rows["bi_BV10"].parts)  # not answered: shown as it came, never guessed

    def test_the_candidates_asked_about_are_the_ten_plus_a_few_spare(self):
        source = FakeSource()
        self.run_with(AppConfig(), source=source)
        self.assertEqual(len(source.parts_asked), 12)  # every bilibili candidate here (12 < 10 + spare)

    def test_a_video_whose_parts_add_up_to_less_than_the_minimum_is_left_out_and_a_spare_takes_its_place(self):
        source = FakeSource()
        source.parts = {"bi_BV11": [600], "bi_BV10": [600]}  # the two biggest are really ten-minute videos
        store, _ = self.run_with(AppConfig(min_duration_sec=3600), source=source)
        ids = [h.video_id for h in store.hot_videos[RUN_ID]]
        self.assertNotIn("bi_BV11", ids)
        self.assertNotIn("bi_BV10", ids)
        self.assertEqual(len(ids), 10)

    def test_a_source_that_cannot_check_parts_never_fails_the_run(self):
        source = FakeSource()

        def boom(ids):
            raise RuntimeError("blocked")

        source.video_parts = boom
        store, obs = self.run_with(AppConfig(), source=source)
        self.assertEqual(len(store.hot_videos[RUN_ID]), 10)
        self.assertTrue(all(h.parts is None for h in store.hot_videos[RUN_ID]))
        self.assertTrue(any("not checked" in m for m in obs.lines))

    def test_the_niche_outranks_a_bigger_video_that_is_not(self):
        plain, _ = self.run_with(AppConfig())
        boosted, _ = self.run_with(AppConfig(niche_terms=("3D国漫",), niche_boost=100.0))
        self.assertFalse(plain.hot_videos[RUN_ID][0].niche)  # the biggest, a vlog, leads
        top = boosted.hot_videos[RUN_ID]
        self.assertTrue(top[0].niche and "3D国漫" in top[0].title)
        first_plain = next(i for i, h in enumerate(top) if not h.niche)
        self.assertTrue(all(h.niche for h in top[:first_plain]))  # every niche video before the first plain one

    def test_series_ranking_becomes_series_rows_with_their_own_ranks(self):
        source = FakeSource(series=[
            HotSeries(1, 12548, "灵笼 第二季", "https://www.bilibili.com/bangumi/play/ss12548", 402_207_839,
                      "9.8分", "全12话"),
            HotSeries(2, 5, "某某", "https://www.bilibili.com/bangumi/play/ss5", 10, None, None),
        ])
        store, _ = self.run_with(AppConfig(bilibili_series_types=(4,)), source=source)
        rows = store.hot_videos[RUN_ID]
        series = [h for h in rows if h.kind == "series"]
        self.assertEqual([(h.rank, h.video_id, h.channel_title, h.views, h.niche) for h in series],
                         [(1, "bi_ss12548", "9.8分 · 全12话", 402_207_839, True), (2, "bi_ss5", None, 10, True)])
        self.assertTrue(all(h.duration_sec is None and h.published_at is None for h in series))
        self.assertEqual([h.rank for h in rows if h.kind == "video"], list(range(1, 11)))  # ranks restart per kind
        self.assertEqual(source.series_args, ((4,),))

    def test_no_series_types_means_no_series_call(self):
        source = FakeSource()
        store, _ = self.run_with(AppConfig(), source=source)
        self.assertEqual(source.series_args, ())
        self.assertTrue(all(h.kind == "video" for h in store.hot_videos[RUN_ID]))

    def test_a_failing_series_ranking_only_warns(self):
        source = FakeSource(series_error=RuntimeError("boom"))
        store, obs = self.run_with(AppConfig(bilibili_series_types=(4,)), source=source)
        self.assertTrue(all(h.kind == "video" for h in store.hot_videos[RUN_ID]))
        self.assertTrue(any("series ranking skipped" in m for m in obs.lines))

    def test_the_card_shows_the_hottest_of_all_platforms(self):
        seen = []

        class SpyChart:
            def render(self, run_id, ideas):
                from application.ports import ChartImage

                seen.append([(i.candidate.video.platform, i.niche) for i in ideas])
                return ChartImage(png=b"\x89PNG", width=1, height=1)

        more, more_ch = self.bilibili_pair()
        source = FakeSource(FakeSource().videos + more, list(FakeSource().channels.values()) + more_ch)
        config = AppConfig(niche_terms=("3D国漫",), niche_boost=100.0)
        uc, _, _ = make(store=FakeStore(config), source=source, host=FakeImageHost())
        uc._chart = SpyChart()
        uc.run()
        self.assertEqual(len(seen[0]), 8)  # the card holds eight videos …
        self.assertEqual([n for _, n in seen[0]], [True] * 6 + [False] * 2)  # the six niche videos lead it
        self.assertIn("youtube", {p for p, _ in seen[0]})  # the rest is the hottest of any platform

    def test_a_hot_list_that_cannot_be_written_never_fails_the_run(self):
        store = FakeStore()
        store.hot_error = RuntimeError("relation hot_videos does not exist")
        more, more_ch = self.bilibili_pair()
        source = FakeSource(FakeSource().videos + more, list(FakeSource().channels.values()) + more_ch)
        uc, store, obs = make(store=store, source=source)
        self.assertEqual(uc.run().status, "ok")
        self.assertTrue(any("hot_videos not written" in line for line in obs.lines))


class RelevanceTest(unittest.TestCase):
    """Only long compilations of the niche are scored: a clip or an off-topic video never reaches the list."""

    @staticmethod
    def videos():
        from domain.models import Channel, VideoSnapshot

        rows = [  # (title, duration in hours)
            ("3D国漫 全集 合集", 6.0), ("修仙动画 合集 8小时", 8.0), ("3D国漫 第1集", 0.4),
            ("Python 教程 全集 合集", 5.0), ("国漫 制作教程 5小时", 5.0), ("旅行 vlog 合集", 6.0),
        ]
        vids, chans = [], []
        for i, (title, hours) in enumerate(rows):
            vids.append(VideoSnapshot(
                id=f"bi_BV{i}", platform="bilibili", native_id=f"BV{i}", url=f"https://www.bilibili.com/video/BV{i}",
                title=title, description="", published_at=NOW - timedelta(hours=30), channel_id=f"bi_{i}",
                duration_sec=int(hours * 3600), thumbnail_url=None, views=90_000 * (i + 1), likes=100, comments=10,
                captured_at=NOW, query_tag="k"))
            chans.append(Channel(id=f"bi_{i}", platform="bilibili", native_id=str(i), title=f"up{i}",
                                 subscriber_count=1000, video_count=5, channel_avg_views=1000.0,
                                 fetched_at=NOW, stale_after=NOW + timedelta(hours=24)))
        return vids, chans

    def run_with(self, **config):
        vids, chans = self.videos()
        base = dict(keywords=(), bilibili_keywords=("国漫",), niche_terms=("国漫", "修仙"),
                    niche_exclude_terms=("教程",))
        source = FakeSource(vids, chans)
        uc, store, obs = make(store=FakeStore(AppConfig(**{**base, **config})), source=source)
        return uc.run(), store, obs, source

    def test_the_default_config_filters_nothing(self):
        _, store, _, _ = self.run_with()
        self.assertEqual(len(store.candidates), 6)

    def test_short_clips_are_dropped_and_the_minimum_reaches_the_searches(self):
        _, store, obs, source = self.run_with(min_duration_sec=4 * 3600)
        titles = sorted(c.video.title for c in store.candidates)
        self.assertNotIn("3D国漫 第1集", titles)
        self.assertEqual(len(titles), 5)
        self.assertEqual(source.min_duration_sec, 4 * 3600)
        self.assertTrue(any("1 shorter than 4 h" in m for m in obs.lines))

    def test_a_video_without_a_duration_is_not_a_long_one(self):
        vids, chans = self.videos()
        vids[0] = vids[0].__class__(**{**vids[0].__dict__, "duration_sec": None})
        uc, store, _ = make(store=FakeStore(AppConfig(keywords=(), min_duration_sec=3600)),
                            source=FakeSource(vids, chans))
        uc.run()
        self.assertNotIn("3D国漫 全集 合集", [c.video.title for c in store.candidates])

    def test_niche_only_keeps_long_animation_and_drops_tutorials_and_other_topics(self):
        _, store, _, _ = self.run_with(min_duration_sec=4 * 3600, niche_only=True)
        self.assertEqual(sorted(c.video.title for c in store.candidates), ["3D国漫 全集 合集", "修仙动画 合集 8小时"])
        hot = [h.title for h in store.hot_videos[RUN_ID] if h.kind == "video"]
        self.assertEqual(sorted(hot), ["3D国漫 全集 合集", "修仙动画 合集 8小时"])

    def test_the_channel_baseline_is_only_asked_for_what_is_kept(self):
        _, _, _, source = self.run_with(min_duration_sec=4 * 3600, niche_only=True)
        self.assertEqual(sorted(i for ids in source.fetched for i in ids), ["bi_0", "bi_1"])


class CadenceTest(unittest.TestCase):
    def test_a_scheduled_run_searches_youtube_only_every_n_hours(self):
        source = FakeSource()
        # 07:17 and every 4 hours: 7 % 4 != 0, so the quota-heavy keyword search is skipped …
        make(store=FakeStore(AppConfig(keywords=("国漫",), youtube_search_every_hours=4)), source=source,
             trigger="schedule")[0].run()
        self.assertEqual(source.collect_args[1], ())
        # … Bilibili still runs, and a manual run or a matching hour searches YouTube
        self.assertEqual(source.bilibili_keywords, ())
        make(store=FakeStore(AppConfig(keywords=("国漫",), youtube_search_every_hours=4)), source=source)[0].run()
        self.assertEqual(source.collect_args[1], ("国漫",))
        make(store=FakeStore(AppConfig(keywords=("国漫",), youtube_search_every_hours=7)), source=source,
             trigger="schedule")[0].run()
        self.assertEqual(source.collect_args[1], ("国漫",))

    def test_the_chart_flag_is_off_too_when_youtube_is_skipped(self):
        source = FakeSource()
        make(store=FakeStore(AppConfig(chart_enabled=True, youtube_search_every_hours=4)), source=source,
             trigger="schedule")[0].run()
        self.assertFalse(source.collect_args[2])

    def test_bilibili_keywords_reach_the_source(self):
        source = FakeSource()
        make(store=FakeStore(AppConfig(bilibili_keywords=("国漫",))), source=source)[0].run()
        self.assertEqual(source.bilibili_keywords, ("国漫",))


class HistoryTest(unittest.TestCase):
    def test_too_similar_to_history_is_dropped(self):
        store = FakeStore()
        store.history_max_cos = 0.85
        r = make(store=store)[0].run()
        self.assertEqual((r.status, r.stats.ideas_count, store.ideas), ("ok", 0, {}))

    def test_history_below_threshold_keeps_idea_with_novelty(self):
        store = FakeStore()
        store.history_max_cos = 0.5
        r = make(store=store)[0].run()
        self.assertEqual(r.stats.ideas_count, 2)
        self.assertTrue(all(abs(i.novelty_score - 0.5) < 1e-9 for i in r.ideas))

    def test_already_proposed_video_is_not_proposed_again(self):
        store = FakeStore()
        store.proposed = {"yt_vid001"}
        r = make(store=store)[0].run()
        self.assertEqual([i.candidate.video.native_id for i in r.ideas], ["vid004"])

    def test_max_ideas_caps_the_digest(self):
        r = make(max_ideas=1)[0].run()
        self.assertEqual([i.candidate.video.native_id for i in r.ideas], ["vid001"])

    def test_known_embedding_with_same_title_is_reused(self):
        store = FakeStore()
        first, _, _ = make(store=store)
        first.run()
        uc2, store, _ = make(store=store)
        embedder = uc2._embedder
        uc2.run()
        self.assertEqual(embedder.calls, [])  # every title hash already stored


class SearchConfigTest(unittest.TestCase):
    def test_chart_flag_and_window_reach_the_source(self):
        store = FakeStore(AppConfig(keywords=("国漫",), chart_enabled=False, search_window_hours=168))
        source = FakeSource()
        make(store=store, source=source)[0].run()
        self.assertEqual(source.collect_args, (("VN",), ("国漫",), False, 168))

    def test_defaults_keep_the_original_behaviour(self):
        source = FakeSource()
        make(source=source)[0].run()
        self.assertEqual(source.collect_args[2:], (True, 48))


class PerPlatformCohortTest(unittest.TestCase):
    """A Bilibili ratio is views per follower, a YouTube one views per average view: never one cohort."""

    @staticmethod
    def bilibili(n):
        from domain.models import Channel, VideoSnapshot

        videos, channels = [], []
        for i in range(n):
            videos.append(VideoSnapshot(
                id=f"bi_BV{i}", platform="bilibili", native_id=f"BV{i}", url=f"https://b/{i}",
                title=f"国漫 第{i}集", description="", published_at=NOW - timedelta(hours=10),
                channel_id=f"bi_{i}", duration_sec=3600, thumbnail_url=None,
                views=1_000 * (i + 1) ** 2, likes=10, comments=1, captured_at=NOW))
            channels.append(Channel(
                id=f"bi_{i}", platform="bilibili", native_id=str(i), title=f"up{i}",
                subscriber_count=2_000_000, video_count=10, channel_avg_views=2_000_000.0,
                fetched_at=NOW, stale_after=NOW + timedelta(hours=24)))
        return videos, channels

    def run_digest(self, with_bilibili):
        videos, channels = FakeSource().videos, list(FakeSource().channels.values())
        if with_bilibili:
            more, more_ch = self.bilibili(4)
            videos, channels = videos + more, channels + more_ch
        uc, store, obs = make(source=FakeSource(videos, channels))
        uc.run()
        return {c.video.id: c for c in store.candidates}, store, obs

    def test_youtube_scores_do_not_move_when_bilibili_joins(self):
        alone, _, _ = self.run_digest(False)
        mixed, _, _ = self.run_digest(True)
        for vid, cand in alone.items():
            self.assertAlmostEqual(mixed[vid].z_score, cand.z_score, places=9)

    def test_bilibili_is_scored_against_its_own_cohort(self):
        from domain import scoring

        mixed, _, _ = self.run_digest(True)
        ratios = [scoring.performance_ratio(1_000 * (i + 1) ** 2, 2_000_000.0) for i in range(4)]
        mu, sigma = scoring.cohort_mu_sigma(ratios)
        for i, ratio in enumerate(ratios):
            self.assertAlmostEqual(mixed[f"bi_BV{i}"].z_score, scoring.z_score(ratio, mu, sigma), places=9)

    def test_the_run_row_records_the_largest_cohort_and_the_log_lists_both(self):
        _, store, obs = self.run_digest(True)
        self.assertEqual(store.runs["run_20261028T071712"]["stats"].cohort.n, 5)  # YouTube's 5 videos, not 9
        self.assertTrue(any(line.startswith("cohorts:") and "bilibili n=4" in line and "youtube n=5" in line
                            for line in obs.lines))

    def test_bilibili_keywords_reach_the_source(self):
        source = FakeSource()
        make(store=FakeStore(AppConfig(bilibili_keywords=("国漫",))), source=source)[0].run()
        self.assertEqual(source.bilibili_keywords, ("国漫",))


class BaselineTest(unittest.TestCase):
    def test_fresh_cached_channels_are_not_refetched(self):
        store = FakeStore()
        store.channels = {c.id: c for c in sample_channels()}
        source = FakeSource()
        make(store=store, source=source)[0].run()
        self.assertEqual(source.fetched, [])

    def test_stale_channels_are_refetched(self):
        store = FakeStore()
        stale = [dataclasses.replace(c, stale_after=NOW - timedelta(hours=1)) for c in sample_channels()]
        store.channels = {c.id: c for c in stale}
        source = FakeSource()
        make(store=store, source=source)[0].run()
        self.assertEqual(len(source.fetched[0]), 5)

    def test_video_without_a_baseline_is_skipped_not_fatal(self):
        source = FakeSource(channels=[c for c in sample_channels() if c.id != "yt_UC_fin20s"])
        uc, store, _ = make(source=source)
        r = uc.run()
        self.assertEqual((r.stats.collected, r.stats.scored), (5, 4))
        self.assertNotIn("yt_vid004", store.videos)

    def test_zero_baseline_is_skipped(self):
        chans = [dataclasses.replace(c, channel_avg_views=0.0) if c.id == "yt_UC_fin20s" else c
                 for c in sample_channels()]
        r = make(source=FakeSource(channels=chans))[0].run()
        self.assertEqual(r.stats.scored, 4)

    def test_empty_collection_is_an_ok_empty_digest(self):
        r = make(source=FakeSource(videos=[]))[0].run()
        self.assertEqual((r.status, r.stats.scored, r.stats.ideas_count), ("ok", 0, 0))


class BudgetTest(unittest.TestCase):
    MB = 1024 * 1024

    def test_over_450mb_stops_writing_candidates(self):
        uc, store, obs = make(store=FakeStore(size=460 * self.MB))
        r = uc.run()
        self.assertEqual(r.status, "ok")
        self.assertEqual(store.candidates, [])
        self.assertEqual(len(store.ideas), 2)

    def test_over_350mb_shrinks_embeddings_ttl(self):
        uc, store, _ = make(store=FakeStore(size=360 * self.MB))
        uc.run()
        self.assertEqual(len(store.candidates), 5)
        self.assertEqual(store.cleaned, (90, 60))


class VelocityWiringTest(unittest.TestCase):
    def test_previous_snapshots_feed_velocity_acceleration_and_early_flag(self):
        store = FakeStore()
        t1, t2 = NOW - timedelta(hours=22), NOW - timedelta(hours=11)
        # 100k → 110k (slow), then 110k → 150k (fast): accelerating
        store.prev["yt_vid001"] = [PreviousSnapshot(110_000, t2), PreviousSnapshot(100_000, t1)]
        make(store=store)[0].run()
        c = next(c for c in store.candidates if c.video.native_id == "vid001")
        v_prev, v_now = 10_000 / 11.0, 40_000 / 11.0
        self.assertAlmostEqual(c.velocity, v_now, places=3)
        self.assertAlmostEqual(c.acceleration, (v_now - v_prev) / 11.0, places=3)
        self.assertGreater(c.acceleration, 0)
        self.assertTrue(c.early_flag)  # only video with a velocity → it is the cohort median

    def test_one_previous_snapshot_gives_velocity_but_no_acceleration(self):
        store = FakeStore()
        store.prev["yt_vid001"] = [PreviousSnapshot(100_000, NOW - timedelta(hours=10))]
        make(store=store)[0].run()
        c = next(c for c in store.candidates if c.video.native_id == "vid001")
        self.assertAlmostEqual(c.velocity, 5_000.0, places=3)
        self.assertIsNone(c.acceleration)
        self.assertFalse(c.early_flag)

    def test_first_sighting_has_no_velocity(self):
        store = FakeStore()
        make(store=store)[0].run()
        self.assertTrue(all(c.velocity is None and not c.early_flag for c in store.candidates))


if __name__ == "__main__":
    unittest.main()
