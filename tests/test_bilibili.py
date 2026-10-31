import unittest
import urllib.error
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from infrastructure import bilibili_api as B
from infrastructure.multi_source import MultiSource
from tests.fakes import NOW, FakeSource

PUB = int((NOW - timedelta(hours=30)).timestamp())


def item(bvid="BV1aa", mid=77, play=123456, pubdate=PUB, **kw):
    base = {"bvid": bvid, "mid": mid, "pubdate": pubdate, "play": play, "like": 900, "review": 45,
            "duration": "72:22", "pic": "//i2.hdslb.com/bfs/archive/x.jpg",
            "title": '<em class="keyword">国漫</em> 全集 &amp; 合集', "description": "简介"}
    return {**base, **kw}


def ok(result):
    return {"code": 0, "data": {"result": result}}


class Script:
    """A fake ``fetch``: replays answers in order (a dict, or an exception to raise); records the URLs."""

    def __init__(self, *answers):
        self.answers, self.urls = list(answers), []

    def __call__(self, url):
        self.urls.append(url)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def http(code):
    return urllib.error.HTTPError("u", code, "Precondition Failed", {}, None)


def source(*answers, waits=(1.0, 2.0)):
    sleeps = []
    return B.BilibiliSource(Script(*answers), sleeps.append, waits, pause=0.5), sleeps


class ParseTest(unittest.TestCase):
    def test_title_drops_highlight_tags_and_entities(self):
        self.assertEqual(B.clean_title('<em class="keyword">国漫</em> A &amp; B'), "国漫 A & B")
        self.assertEqual(B.clean_title("全集 <合集> 第1集 <b>"), "全集 <合集> 第1集 <b>")  # not Bilibili's markup

    def test_duration(self):
        self.assertEqual(B.parse_duration("72:22"), 72 * 60 + 22)
        self.assertEqual(B.parse_duration("1:02:03"), 3723)
        for bad in ("", None, "abc", "1:2:3:4", "0:00"):
            self.assertIsNone(B.parse_duration(bad))


class SearchTest(unittest.TestCase):
    def test_a_result_becomes_a_snapshot(self):
        src, _ = source(ok([item()]))
        [v] = src.collect(("国漫",), NOW, 48)
        self.assertEqual((v.id, v.platform, v.native_id), ("bi_BV1aa", "bilibili", "BV1aa"))
        self.assertEqual(v.url, "https://www.bilibili.com/video/BV1aa")
        self.assertEqual((v.views, v.likes, v.comments, v.duration_sec), (123456, 900, 45, 4342))
        self.assertEqual(v.channel_id, "bi_77")
        self.assertEqual(v.title, "国漫 全集 & 合集")
        self.assertEqual(v.thumbnail_url, "https://i2.hdslb.com/bfs/archive/x.jpg")
        self.assertEqual(v.query_tag, "国漫")
        self.assertEqual(v.published_at.utcoffset(), timedelta(hours=7))  # Vietnam time
        self.assertAlmostEqual(v.age_hours, 30, delta=0.01)

    def test_a_minimum_of_an_hour_asks_for_long_videos_on_two_pages(self):
        src, _ = source(ok([item(bvid="BV1")]), ok([item(bvid="BV2")]))
        got = src.collect(("国漫",), NOW, 48, min_duration_sec=4 * 3600)
        qs = [parse_qs(urlparse(u).query) for u in src._fetch.urls]
        self.assertEqual([q["page"] for q in qs], [["1"], ["2"]])
        self.assertTrue(all(q["duration"] == ["4"] for q in qs))  # Bilibili's "longer than 60 minutes"
        self.assertEqual([v.native_id for v in got], ["BV1", "BV2"])

    def test_part_durations_lists_each_part_and_leaves_out_what_it_could_not_check(self):
        pages = {"code": 0, "data": [{"page": 1, "duration": 420}, {"page": 2, "duration": 34260}]}
        src, _ = source(pages, {"code": -404, "message": "no"}, {"code": -404}, {"code": -404}, {"code": -404})
        got = src.part_durations(["BV1", "BV2"])
        self.assertEqual(got, {"BV1": [420, 34260]})
        self.assertIn("BV2", " ".join(src.warnings))
        self.assertIn("bvid=BV1", src._fetch.urls[0])
        self.assertIn("/x/player/pagelist", src._fetch.urls[0])

    def test_part_durations_through_the_multi_source_uses_the_prefixed_ids(self):
        src, _ = source({"code": 0, "data": [{"duration": 100}, {"duration": 200}]})
        multi = MultiSource(FakeSource(), src)
        self.assertEqual(multi.video_parts(["bi_BV1", "yt_x"]), {"bi_BV1": [100, 200]})

    def test_pages_can_be_asked_for_without_a_minimum(self):
        src, _ = source(ok([item(bvid="BV1")]), ok([item(bvid="BV2")]))
        got = src.collect(("西游记 动画",), NOW, 2160, pages=2)
        qs = [parse_qs(urlparse(u).query) for u in src._fetch.urls]
        self.assertEqual([q["page"] for q in qs], [["1"], ["2"]])
        self.assertTrue(all("duration" not in q for q in qs))  # every length
        self.assertEqual([v.native_id for v in got], ["BV1", "BV2"])

    def test_no_minimum_keeps_one_unfiltered_page(self):
        src, _ = source(ok([]))
        src.collect(("国漫",), NOW, 48)
        q = parse_qs(urlparse(src._fetch.urls[0]).query)
        self.assertNotIn("duration", q)
        self.assertEqual(len(src._fetch.urls), 1)

    def test_the_window_is_sent_as_publication_times(self):
        src, _ = source(ok([]))
        src.collect(("国漫",), NOW, 168)
        q = parse_qs(urlparse(src._fetch.urls[0]).query)
        self.assertEqual(q["order"], ["click"])
        self.assertEqual(int(q["pubtime_end_s"][0]) - int(q["pubtime_begin_s"][0]), 168 * 3600)
        self.assertEqual(q["keyword"], ["国漫"])

    def test_a_video_found_by_two_keywords_is_kept_once(self):
        src, sleeps = source(ok([item()]), ok([item(), item("BV1bb", 78)]))
        found = src.collect(("a", "b"), NOW, 48)
        self.assertEqual(sorted(v.native_id for v in found), ["BV1aa", "BV1bb"])
        self.assertEqual(sleeps, [0.5])  # one polite pause between the two keywords

    def test_incomplete_results_are_dropped(self):
        src, _ = source(ok([item(bvid=""), item(mid=None), item(pubdate=None), item("BV1ok")]))
        self.assertEqual([v.native_id for v in src.collect(("k",), NOW, 48)], ["BV1ok"])

    def test_a_412_is_retried_after_a_wait(self):
        src, sleeps = source(http(412), {"code": -412, "message": "request blocked"}, ok([item()]))
        self.assertEqual(len(src.collect(("k",), NOW, 48)), 1)
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(src.warnings, [])

    def test_the_352_risk_control_answer_is_retried_too(self):
        src, _ = source({"code": -352, "message": "risk"}, ok([item()]))
        self.assertEqual(len(src.collect(("k",), NOW, 48)), 1)

    def test_a_keyword_that_stays_blocked_is_skipped_and_reported(self):
        src, _ = source(http(412), http(412), http(412), ok([item()]))
        found = src.collect(("blocked", "fine"), NOW, 48)
        self.assertEqual([v.native_id for v in found], ["BV1aa"])  # the other keyword still counts
        self.assertEqual(len(src.warnings), 1)
        self.assertIn("'blocked' skipped", src.warnings[0])
        self.assertIn("HTTP 412", src.warnings[0])

    def test_a_network_error_is_retried_not_raised(self):
        src, _ = source(urllib.error.URLError("down"), ok([item()]))
        self.assertEqual(len(src.collect(("k",), NOW, 48)), 1)


def listed(bvid="BV9zz", mid=88, view=5_000_000, **kw):
    base = {"bvid": bvid, "owner": {"mid": mid, "name": "某UP主"}, "pubdate": PUB, "duration": 874,
            "pic": "http://i0.hdslb.com/x.jpg", "title": "《崩坏：星穹铁道》PV", "desc": "简介",
            "stat": {"view": view, "like": 3000, "reply": 120}, "tname": "手机游戏"}
    return {**base, **kw}


class TrendingTest(unittest.TestCase):
    def test_both_hot_lists_are_read_de_duplicated_and_tagged(self):
        popular = {"code": 0, "data": {"list": [listed("BV1"), listed("BV2", owner={})]}}
        ranking = {"code": 0, "data": {"list": [listed("BV1"), listed("BV3", mid=99)]}}
        src, sleeps = source(popular, ranking)
        got = src.trending(NOW)
        self.assertEqual([v.native_id for v in got], ["BV1", "BV3"])  # BV2 has no owner; BV1 listed twice
        v = got[0]
        self.assertEqual((v.channel_id, v.views, v.likes, v.comments, v.duration_sec), ("bi_88", 5_000_000, 3000,
                                                                                        120, 874))
        self.assertEqual((v.query_tag, v.title, v.description), ("trending", "《崩坏：星穹铁道》PV", "简介"))
        urls = src._fetch.urls
        self.assertIn("/x/web-interface/popular?ps=50&pn=1", urls[0])
        self.assertIn("/x/web-interface/ranking/v2?rid=0&type=all", urls[1])
        self.assertEqual(sleeps, [0.5])  # the pause between the two lists

    def test_a_blocked_list_is_reported_and_the_other_still_read(self):
        ranking = {"code": 0, "data": {"list": [listed("BV3")]}}
        src, _ = source(http(412), http(412), http(412), ranking)
        self.assertEqual([v.native_id for v in src.trending(NOW)], ["BV3"])
        self.assertIn("综合热门 skipped: HTTP 412", " ".join(src.warnings))


class ChannelTest(unittest.TestCase):
    def card(self, fans=1_434_024):
        return {"code": 0, "data": {"card": {"fans": fans, "name": "某UP主"}, "archive_count": 44}}

    def test_followers_are_the_baseline(self):
        src, _ = source(self.card())
        [ch] = src.fetch_channels(["bi_2"], NOW)
        self.assertEqual((ch.id, ch.platform, ch.native_id, ch.title), ("bi_2", "bilibili", "2", "某UP主"))
        self.assertEqual((ch.channel_avg_views, ch.subscriber_count, ch.video_count), (1_434_024.0, 1_434_024, 44))
        self.assertEqual(ch.stale_after - ch.fetched_at, timedelta(hours=24))
        self.assertIn("mid=2", src._fetch.urls[0])

    def test_a_channel_without_followers_has_a_zero_baseline_so_it_is_skipped_later(self):
        src, _ = source(self.card(fans=0))
        self.assertEqual(src.fetch_channels(["bi_2"], NOW)[0].channel_avg_views, 0.0)

    def test_a_blocked_channel_is_reported_not_fatal(self):
        src, _ = source(http(412), http(412), http(412), self.card())
        out = src.fetch_channels(["bi_1", "bi_2"], NOW)
        self.assertEqual([c.id for c in out], ["bi_2"])
        self.assertIn("channel 1 skipped", src.warnings[0])


class Notes:
    def __init__(self):
        self.infos, self.warns = [], []

    def info(self, m):
        self.infos.append(m)

    def warn(self, m):
        self.warns.append(m)


class FakeBili:
    def __init__(self, videos=(), warnings=()):
        self.videos, self.warnings, self.calls = list(videos), list(warnings), []

    def collect(self, keywords, now, window_hours, min_duration_sec=0, pages=None):
        self.calls.append((keywords, window_hours) + ((min_duration_sec, pages) if pages else ()))
        return self.videos

    def trending(self, now):
        self.calls.append("trending")
        return self.videos

    def series_ranking(self, season_types):
        self.calls.append(("series", season_types))
        return getattr(self, "ranked_series", [])

    def fetch_channels(self, ids, now):
        self.calls.append(("channels", tuple(ids)))
        return []


def series(season_id=12548, rank=1, **kw):
    base = {"season_id": season_id, "rank": rank, "title": "灵笼 第二季", "rating": "9.8分",
            "url": f"https://www.bilibili.com/bangumi/play/ss{season_id}",
            "new_ep": {"index_show": "全12话"}, "stat": {"view": 402_207_839}}
    return {**base, **kw}


class SeriesRankingTest(unittest.TestCase):
    def test_a_series_entry_is_parsed(self):
        src, _ = source({"code": 0, "result": {"list": [series(), series(5, 2, rating=None, new_ep={})]}})
        got = src.series_ranking((4,))
        self.assertEqual((got[0].rank, got[0].season_id, got[0].views, got[0].rating, got[0].episodes),
                         (1, 12548, 402_207_839, "9.8分", "全12话"))
        self.assertEqual((got[1].rating, got[1].episodes), (None, None))
        self.assertIn("season_type=4", src._fetch.urls[0])

    def test_entries_without_an_id_title_or_https_url_are_dropped(self):
        bad = [series(season_id=None), series(2, title=""), series(3, url="http://x"), series(4)]
        src, _ = source({"code": 0, "result": {"list": bad}})
        self.assertEqual([s.season_id for s in src.series_ranking((4,))], [4])

    def test_the_url_is_built_from_the_season_when_missing(self):
        src, _ = source({"code": 0, "result": {"list": [series(url=None)]}})
        self.assertEqual(src.series_ranking((4,))[0].url, "https://www.bilibili.com/bangumi/play/ss12548")

    def test_a_limit_keeps_only_the_top(self):
        src, _ = source({"code": 0, "result": {"list": [series(i, i) for i in range(1, 30)]}})
        self.assertEqual(len(src.series_ranking((4,), limit=10)), 10)

    def test_an_unreachable_ranking_warns_and_returns_nothing(self):
        src, _ = source(*[http(412)] * 3)
        self.assertEqual(src.series_ranking((4,)), [])
        self.assertTrue(any("series ranking 4 skipped" in w for w in src.warnings))

    def test_no_types_asks_nothing(self):
        src, _ = source()
        self.assertEqual(src.series_ranking(()), [])
        self.assertEqual(src._fetch.urls, [])


class MultiSourceTest(unittest.TestCase):
    def bi_video(self):
        return B.BilibiliSource._parse(item(), NOW, "k")

    def test_bilibili_is_skipped_without_keywords(self):
        bili = FakeBili([self.bi_video()])
        got = MultiSource(FakeSource(), bili).collect(("VN",), ("k",), NOW)
        self.assertEqual(bili.calls, [])
        self.assertTrue(all(v.platform == "youtube" for v in got))

    def test_bilibili_keywords_add_its_videos_after_youtubes(self):
        bili, notes = FakeBili([self.bi_video()], ["Bilibili search 'x' skipped: HTTP 412"]), Notes()
        got = MultiSource(FakeSource(), bili, notes).collect(("VN",), ("k",), NOW, True, 168, ("国漫",))
        self.assertEqual(bili.calls, [(("国漫",), 168)])
        self.assertEqual(got[-1].id, "bi_BV1aa")
        self.assertEqual(len(got), 6)
        self.assertEqual(notes.warns, ["Bilibili search 'x' skipped: HTTP 412"])
        self.assertEqual(bili.warnings, [])  # drained: reported once, not on every later call

    def test_a_search_asks_bilibili_alone_for_two_pages_of_every_length(self):
        bili, notes = FakeBili([self.bi_video()], ["Bilibili search '西游记' skipped: HTTP 412"]), Notes()
        yt = FakeSource(error=RuntimeError("YouTube must not be asked"))
        multi = MultiSource(yt, bili, notes)
        self.assertEqual([v.id for v in multi.search("西游记 动画", NOW, 2160)], ["bi_BV1aa"])
        self.assertEqual([v.id for v in multi.trending(NOW)], ["bi_BV1aa"])
        self.assertEqual(bili.calls, [(("西游记 动画",), 2160, 0, 2), "trending"])
        self.assertEqual(notes.warns, ["Bilibili search '西游记' skipped: HTTP 412"])
        self.assertEqual((MultiSource(yt).search("x", NOW, 1), MultiSource(yt).trending(NOW)), ([], []))

    def test_youtube_failure_still_fails_the_run(self):
        with self.assertRaises(RuntimeError):
            MultiSource(FakeSource(error=RuntimeError("quota")), FakeBili()).collect(("VN",), (), NOW)

    def test_channels_are_routed_by_prefix(self):
        yt, bili = FakeSource(), FakeBili()
        yt.fetch_channels = lambda ids, now: [f"yt:{i}" for i in ids]
        out = MultiSource(yt, bili).fetch_channels(["yt_UC1", "bi_9", "yt_UC2"], NOW)
        self.assertEqual(out, ["yt:yt_UC1", "yt:yt_UC2"])
        self.assertEqual(bili.calls, [("channels", ("bi_9",))])

    def test_without_a_bilibili_adapter_its_channels_are_ignored(self):
        yt = FakeSource()
        yt.fetch_channels = lambda ids, now: []
        self.assertEqual(MultiSource(yt).fetch_channels(["bi_9"], NOW), [])


if __name__ == "__main__":
    unittest.main()


class CheckBilibiliTest(unittest.TestCase):
    def run_check(self, source):
        from application.check_bilibili import CheckBilibili

        notes = Notes()
        return CheckBilibili(source, notes, lambda: NOW).run(), notes

    def test_ok_when_the_search_and_the_card_answer(self):
        src, _ = source(ok([item()]), {"code": 0, "data": {"card": {"fans": 5, "name": "x"}, "archive_count": 1}})
        done, notes = self.run_check(src)
        self.assertTrue(done)
        self.assertIn("1 video(s)", notes.infos[0])
        self.assertIn("1 channel card(s)", notes.infos[0])

    def test_not_ok_and_reported_when_bilibili_blocks_the_runner(self):
        src, _ = source(http(412), http(412), http(412))
        done, notes = self.run_check(src)
        self.assertFalse(done)
        self.assertIn("HTTP 412", notes.warns[0])
