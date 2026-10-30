"""In-memory adapters and the docs/04 sample cohort, shared by the use-case tests."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from application.ports import IdeaBrief
from domain.clock import VN_TZ
from domain.models import (
    AppConfig,
    Candidate,
    Channel,
    Idea,
    Media,
    PreviousSnapshot,
    RunStats,
    VideoSnapshot,
)

NOW = datetime(2026, 10, 28, 7, 17, 12, tzinfo=VN_TZ)  # 07:17 giờ Việt Nam


def vn(*args) -> datetime:
    return datetime(*args, tzinfo=VN_TZ)


# (id, title, published_at, channel, views, likes, comments, channel title, channel avg)
SAMPLE = [
    ("vid001", "Cách tạo Bot Python lấy dữ liệu TikTok tự động", vn(2026, 10, 28, 2, 0),
     "UC_pythonlab", 150_000, 9_200, 410, "Python Lab VN", 5_000.0),
    ("vid002", "Hướng dẫn viết Bot Python cào video TikTok đơn giản", vn(2026, 10, 27, 22, 30),
     "UC_codevn", 120_000, 6_800, 350, "Code Dạo VN", 4_000.0),
    ("vid003", "Vlog một ngày ăn uống tại Đà Nẵng", vn(2026, 10, 26, 19, 0),
     "UC_foodtrip", 8_000, 310, 25, "Ăn Khắp Việt Nam", 10_000.0),
    ("vid004", "Bí quyết quản lý tài chính cho sinh viên năm 2026", vn(2026, 10, 27, 15, 0),
     "UC_fin20s", 95_000, 6_100, 380, "Tài chính 20s", 3_000.0),
    ("vid005", "Video ca nhạc hài hước triệu views", vn(2026, 10, 27, 1, 17),
     "UC_bigmusic", 2_000_000, 85_000, 4_200, "Big Music VN", 1_800_000.0),
]

VECTORS = {
    "vid001": [1.0, 0.0, 0.0],
    "vid002": [0.81, math.sqrt(1 - 0.81**2), 0.0],  # cos 0.81 with vid001 (docs/05)
    "vid003": [0.0, 0.0, 1.0],
    "vid004": [0.0, 0.0, 1.0],
    "vid005": [0.0, 1.0, 0.0],
}


def sample_videos(now: datetime = NOW) -> list[VideoSnapshot]:
    return [
        VideoSnapshot(
            id=f"yt_{vid}", platform="youtube", native_id=vid,
            url=f"https://www.youtube.com/watch?v={vid}", title=title, description="",
            published_at=pub, channel_id=f"yt_{ch}", duration_sec=600, thumbnail_url=None,
            views=views, likes=likes, comments=comments, captured_at=now,
        )
        for vid, title, pub, ch, views, likes, comments, _, _ in SAMPLE
    ]


def sample_channels(now: datetime = NOW) -> list[Channel]:
    return [
        Channel(
            id=f"yt_{ch}", platform="youtube", native_id=ch, title=ctitle, subscriber_count=1000,
            video_count=100, channel_avg_views=avg, fetched_at=now,
            stale_after=now + timedelta(hours=24),
        )
        for _, _, _, ch, _, _, _, ctitle, avg in SAMPLE
    ]


def good_llm(**override) -> dict:
    out = {
        "summary": "Tóm tắt.", "why_viral": "Kênh nhỏ đạt nhiều view.", "hook": "Bạn đã biết chưa?",
        "angles": ["Góc một", "Góc hai", "Góc ba"], "format": "review", "risk": "reused",
    }
    out.update(override)
    return out


class FakeSource:
    def __init__(self, videos=None, channels=None, error: Exception | None = None):
        self.videos = sample_videos() if videos is None else videos
        self.channels = {c.id: c for c in (sample_channels() if channels is None else channels)}
        self.error = error
        self.fetched: list[list[str]] = []

    def collect(self, regions, keywords, now, chart_enabled=True, window_hours=48, bilibili_keywords=()):
        self.collect_args = (regions, keywords, chart_enabled, window_hours)
        self.bilibili_keywords = bilibili_keywords
        if self.error:
            raise self.error
        return list(self.videos)

    def fetch_channels(self, channel_ids, now):
        self.fetched.append(list(channel_ids))
        return [self.channels[i] for i in channel_ids if i in self.channels]


class FakeEmbedder:
    def __init__(self, vectors=None):
        self.vectors = vectors or VECTORS
        self.calls: list[list[str]] = []

    def encode(self, texts):
        self.calls.append(list(texts))
        by_title = {title: VECTORS_BY_TITLE[title] for title in texts}
        return [by_title[t] for t in texts]


VECTORS_BY_TITLE = {row[1]: VECTORS[f"{row[0]}"] for row in SAMPLE}


class FakeWriter:
    def __init__(self, outputs=None, error: Exception | None = None):
        self.outputs = list(outputs) if outputs is not None else None
        self.error = error
        self.briefs: list[IdeaBrief] = []

    def write(self, brief):
        self.briefs.append(brief)
        if self.error:
            raise self.error
        if self.outputs is None:
            return good_llm()
        return self.outputs.pop(0)


class FakeImageHost:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.uploads: list[str] = []

    def upload(self, png, filename):
        if self.fail:
            raise OSError("host down")
        self.uploads.append(filename)
        return f"https://img.example/{filename}"


class FakeChart:
    def render(self, run_id, ideas):
        from application.ports import ChartImage

        return ChartImage(png=b"\x89PNG-" + run_id.encode(), width=10, height=5)


class FakeStore:
    """Implements DigestStore in memory and records what was written."""

    def __init__(self, config: AppConfig | None = None, size: int | None = None):
        self.config = config or AppConfig(keywords=("python bot",), regions=("VN",))
        self.size = size
        self.runs: dict[str, dict] = {}
        self.channels: dict[str, Channel] = {}
        self.videos: dict[str, VideoSnapshot] = {}
        self.snapshots: list[tuple[str, str, VideoSnapshot]] = []
        self.candidates: list[Candidate] = []
        self.embeddings: dict[str, tuple[str, str, list[float]]] = {}
        self.history_max_cos: float | None = None
        self.proposed: set[str] = set()
        self.ideas: dict[tuple[str, str], Idea] = {}
        self.media: dict[str, Media] = {}
        self.prev: dict[str, list[PreviousSnapshot]] = {}
        self.cleaned: tuple[int, int] | None = None
        self.nearest_calls: list[list[str]] = []

    def get_app_config(self):
        return self.config

    def open_run(self, run_id, trigger, git_sha, region, started_at):
        self.runs[run_id] = {"status": "running", "trigger": trigger, "git_sha": git_sha,
                             "region": region}

    def finish_run(self, run_id, status, finished_at, stats: RunStats, error, chart_media_id):
        self.runs[run_id].update(status=status, stats=stats, error=error,
                                 chart_media_id=chart_media_id)

    def get_channels(self, channel_ids):
        return {i: self.channels[i] for i in channel_ids if i in self.channels}

    def upsert_channels(self, channels):
        self.channels.update({c.id: c for c in channels})

    def upsert_videos(self, videos, run_id, now):
        self.videos.update({v.id: v for v in videos})

    def insert_snapshots(self, videos, run_id, ttl_days):
        self.snapshots.extend((run_id, ttl_days, v) for v in videos)  # type: ignore[arg-type]

    def previous_snapshots(self, video_ids, before, limit):
        return {i: self.prev.get(i, [])[:limit] for i in video_ids}

    def insert_candidates(self, run_id, candidates, ttl_days):
        self.candidates.extend(candidates)

    def get_embeddings(self, video_ids):
        return {i: (self.embeddings[i][0], self.embeddings[i][2])
                for i in video_ids if i in self.embeddings}

    def upsert_embeddings(self, rows, now):
        for vid, text_hash, source, vec in rows:
            self.embeddings[vid] = (text_hash, source, vec)

    def nearest_history(self, vector, days, exclude_ids):
        self.nearest_calls.append(list(exclude_ids))
        return self.history_max_cos

    def proposed_video_ids(self, days):
        return set(self.proposed)

    def insert_ideas(self, run_id, ideas):
        for i in ideas:
            self.ideas[(run_id, i.video_id)] = i

    def update_idea_llm(self, run_id, video_id, llm):
        self.ideas[(run_id, video_id)].llm = llm

    def find_media(self, sha256):
        return next((m for m in self.media.values() if m.sha256 == sha256), None)

    def insert_media(self, media):
        self.media[media.id] = media

    def cleanup(self, ttl_days, embeddings_ttl_days):
        self.cleaned = (ttl_days, embeddings_ttl_days)
        return {"snapshots": 0}

    def db_size_bytes(self):
        return self.size
