"""Ports the use cases depend on; adapters live in infrastructure/."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.models import (
    AppConfig,
    Candidate,
    Channel,
    HotSeries,
    HotVideo,
    Idea,
    Media,
    PreviousSnapshot,
    RunStats,
    VideoSnapshot,
)


@dataclass(frozen=True)
class IdeaBrief:
    """What Gemini is allowed to read about one leader (docs/02 · Gemini)."""

    title: str
    description: str
    channel_title: str
    url: str
    views: int
    likes: int
    comments: int
    age_hours: float
    performance_ratio: float
    duplicates_count: int


@dataclass(frozen=True)
class ChartImage:
    png: bytes
    width: int
    height: int


class VideoSource(Protocol):
    def collect(
        self,
        regions: tuple[str, ...],
        keywords: tuple[str, ...],
        now: datetime,
        chart_enabled: bool = True,
        window_hours: int = 48,
        bilibili_keywords: tuple[str, ...] = (),
    ) -> list[VideoSnapshot]:
        """A1 chart per region (when enabled) + A2 keyword search over the window, plus Bilibili search
        for ``bilibili_keywords``; de-duplicated."""

    def hot_series(self, season_types: tuple[int, ...], now: datetime) -> list[HotSeries]:
        """Bilibili's live series ranking (4 = 国创); empty when it is off or unreachable."""

    def fetch_channels(self, channel_ids: list[str], now: datetime) -> list[Channel]:
        """A3 baselines for the channels the cache does not cover (``yt_UC…`` / ``bi_<mid>`` ids)."""


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class IdeaWriter(Protocol):
    def write(self, brief: IdeaBrief) -> object:
        """Raw JSON object from the LLM (validated by the use case, which retries once)."""


class ImageHost(Protocol):
    def upload(self, png: bytes, filename: str) -> str:
        """POST the image, return its public URL."""


class ChartRenderer(Protocol):
    def render(self, run_id: str, ideas: list[Idea]) -> ChartImage | None: ...


@dataclass(frozen=True)
class RunPoint:
    """One past run, for the timeline chart."""

    started_at: datetime
    collected: int
    outliers: int
    ideas: int


@dataclass(frozen=True)
class AnalysisImage:
    slug: str
    caption: str  # Vietnamese title, shown by estfstudio
    position: int  # 1 is the top-ideas chart
    png: bytes
    width: int
    height: int


class AnalysisRenderer(Protocol):
    def render(
        self,
        run_id: str,
        now: datetime,
        candidates: list[Candidate],
        ideas: list[Idea],
        history: list[RunPoint],
    ) -> list[AnalysisImage]:
        """Every analysis chart the data can support (a chart with too little data is left out)."""


class DigestStore(Protocol):
    def get_app_config(self) -> AppConfig: ...

    def open_run(
        self, run_id: str, trigger: str, git_sha: str, region: str, started_at: datetime
    ) -> None: ...

    def finish_run(
        self,
        run_id: str,
        status: str,
        finished_at: datetime,
        stats: RunStats,
        error: dict | None,
        chart_media_id: str | None,
    ) -> None: ...

    def get_channels(self, channel_ids: list[str]) -> dict[str, Channel]: ...

    def upsert_channels(self, channels: list[Channel]) -> None: ...

    def upsert_videos(self, videos: list[VideoSnapshot], run_id: str, now: datetime) -> None: ...

    def insert_snapshots(
        self, videos: list[VideoSnapshot], run_id: str, ttl_days: int
    ) -> None: ...

    def previous_snapshots(
        self, video_ids: list[str], before: datetime, limit: int
    ) -> dict[str, list[PreviousSnapshot]]:
        """Newest first, strictly before ``before``."""

    def insert_candidates(self, run_id: str, candidates: list[Candidate], ttl_days: int) -> None: ...

    def get_embeddings(self, video_ids: list[str]) -> dict[str, tuple[str, list[float]]]:
        """``{video_id: (text_hash, vector)}`` — only for the few outliers of this run."""

    def upsert_embeddings(
        self, rows: list[tuple[str, str, str, list[float]]], now: datetime
    ) -> None:
        """Rows are ``(video_id, text_hash, source, vector)``."""

    def nearest_history(
        self, vector: list[float], days: int, exclude_ids: list[str]
    ) -> float | None:
        """Max cosine similarity against embeddings updated in the last ``days`` days."""

    def proposed_video_ids(self, days: int) -> set[str]: ...

    def recent_runs(self, limit: int) -> list[RunPoint]:
        """Newest ``limit`` finished runs, oldest first."""

    def insert_ideas(self, run_id: str, ideas: list[Idea]) -> None: ...

    def insert_hot_videos(self, run_id: str, rows: list[HotVideo]) -> None: ...

    def update_idea_llm(self, run_id: str, video_id: str, llm: dict) -> None: ...

    def find_media(self, sha256: str) -> Media | None: ...

    def insert_media(self, media: Media) -> None: ...

    def cleanup(self, ttl_days: int, embeddings_ttl_days: int) -> dict[str, int]: ...

    def db_size_bytes(self) -> int | None: ...
