"""Entities (docs/01 · domain/): plain dataclasses, no I/O, stdlib only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from domain.clock import to_vn

SUPPORTED_SCHEMA_VERSION = 1

LLM_FORMATS = ("long", "short", "compilation", "review")
LLM_RISKS = ("copyright", "reused", "kids", "sensitive")


@dataclass(frozen=True)
class AppConfig:
    """The single ``app_config`` row (docs/04): thresholds live in the DB, not the code."""

    schema_version: int = 1
    regions: tuple[str, ...] = ("VN",)
    keywords: tuple[str, ...] = ()
    z_threshold: float = 1.5
    relaxed_z_threshold: float = 0.5
    cosine_threshold: float = 0.70
    history_cosine_threshold: float = 0.80
    decay_lambda: float = 0.05
    engagement_like_w: float = 1.5
    engagement_comment_w: float = 3.0
    bayes_c: int = 1000
    min_cohort_n: int = 20
    snapshot_ttl_days: int = 90
    llm_enabled: bool = True
    chart_enabled: bool = True  # A1 mostPopular chart; off for a niche so the cohort stays on topic
    search_window_hours: int = 48  # A2: only videos published within this window
    bilibili_keywords: tuple[str, ...] = ()  # Chinese search terms for Bilibili; empty = Bilibili off
    bilibili_series_types: tuple[int, ...] = ()  # Bilibili series rankings (4 = 国创); empty = none
    niche_terms: tuple[str, ...] = ()  # a title/description with one of these is in the niche
    niche_boost: float = 1.0  # idea priority multiplier for the niche (viral_score itself is not changed)
    niche_exclude_terms: tuple[str, ...] = ()  # a title with one of these is never the niche (tutorials)
    niche_only: bool = False  # drop every video that is not the niche before scoring
    min_duration_sec: int = 0  # drop (and ask the platforms for) videos shorter than this; 0 = any length
    youtube_search_every_hours: int = 1  # YouTube keyword search only when hour % N == 0 (quota)
    analysis_every_hours: int = 1  # analysis charts only when hour % N == 0 (image host load)


@dataclass(frozen=True)
class Channel:
    id: str  # yt_UC…
    platform: str
    native_id: str
    title: str
    subscriber_count: int | None
    video_count: int | None
    channel_avg_views: float
    fetched_at: datetime
    stale_after: datetime

    def is_stale(self, now: datetime) -> bool:
        return now > self.stale_after


@dataclass(frozen=True)
class VideoSnapshot:
    """A video as seen at ``captured_at`` (identity + counters)."""

    id: str  # yt_vid001
    platform: str
    native_id: str
    url: str
    title: str
    description: str
    published_at: datetime
    channel_id: str
    duration_sec: int | None
    thumbnail_url: str | None
    views: int
    likes: int
    comments: int
    captured_at: datetime
    query_tag: str | None = None

    @property
    def age_hours(self) -> float:
        return max((self.captured_at - self.published_at).total_seconds() / 3600.0, 0.0)


@dataclass(frozen=True)
class PreviousSnapshot:
    views: int
    captured_at: datetime


@dataclass
class Candidate:
    """L1 result for one video of one run (``candidates`` row)."""

    video: VideoSnapshot
    channel_avg_views: float
    performance_ratio: float
    z_score: float
    engagement: float
    time_decay: float
    viral_score: float
    velocity: float | None = None
    acceleration: float | None = None
    early_flag: bool = False
    passed_z: bool = False
    z_threshold: float | None = None  # θ of its platform's cohort (the analysis chart draws it)
    title_vi: str | None = None  # the title in Vietnamese, for the charts (None = not translated)

    @property
    def shown_title(self) -> str:
        """What a Vietnamese reader sees: the translated title, else the original."""
        return self.title_vi or self.video.title


@dataclass
class Idea:
    """L2 leader of a cluster (``ideas`` row)."""

    candidate: Candidate
    channel_title: str
    cluster_id: str
    duplicates_count: int = 0
    niche: bool = False  # matched niche_terms / a niche ranking (run-time only, not stored)
    novelty_score: float | None = None
    llm: dict | None = None
    embedding: list[float] = field(default_factory=list, repr=False)

    @property
    def video_id(self) -> str:
        return self.candidate.video.id


@dataclass
class CohortStats:
    n: int
    mu_ratio: float | None
    sigma_ratio: float | None
    median_engagement: float | None
    z_threshold_used: float


@dataclass
class RunStats:
    collected: int = 0
    scored: int = 0
    outliers: int = 0
    ideas_count: int = 0
    cohort: CohortStats | None = None
    duration_ms: int | None = None


def run_id_of(now: datetime) -> str:
    """``run_`` + Vietnam time ``YYYYMMDDTHHMMSS`` (sortable; docs/03)."""
    return "run_" + to_vn(now).strftime("%Y%m%dT%H%M%S")


def video_id_of(platform_prefix: str, native_id: str) -> str:
    return f"{platform_prefix}_{native_id}"


def expire_at(captured_at: datetime, ttl_days: int) -> datetime:
    return captured_at + timedelta(days=ttl_days)


@dataclass(frozen=True)
class HotSeries:
    """One entry of Bilibili's live 国创 (Chinese animation) series ranking."""

    rank: int  # as Bilibili ranks it, 1 = hottest
    season_id: int
    title: str
    url: str
    views: int  # total plays of the whole series
    rating: str | None  # "9.8分"
    episodes: str | None  # "全12话" / "更新至第5话"


@dataclass(frozen=True)
class HotVideo:
    """A row of ``hot_videos``, flat so a reader needs no join. ``kind`` is ``video`` or ``series``."""

    kind: str
    rank: int  # 1 = hottest within its kind
    video_id: str
    platform: str
    title: str
    url: str
    channel_title: str | None
    views: int
    duration_sec: int | None
    published_at: datetime | None
    niche: bool
    viral_score: float
    parts: int | None = None  # parts (分P) of the video, None = not checked; duration_sec is their total
    first_part_sec: int | None = None  # what the player opens on: part 1
    title_vi: str | None = None  # the title in Vietnamese (None = not translated)


@dataclass(frozen=True)
class Media:
    """A row of ``media``: an image already on the image host (URL + sha256, never the bytes)."""

    id: str  # 'img_' + first 16 hex of sha256
    owner: str  # flashtrend | estfstudio
    kind: str  # thumbnail | chart | cover
    url: str
    host: str
    sha256: str
    bytes: int
    width: int | None = None
    height: int | None = None
    video_id: str | None = None
    run_id: str | None = None
    caption: str | None = None  # analysis charts: Vietnamese title of the chart
    position: int | None = None  # analysis charts: display order within a run


MAX_IMAGE_BYTES = 2_000_000


def media_id_of(sha256_hex: str) -> str:
    return "img_" + sha256_hex[:16]
