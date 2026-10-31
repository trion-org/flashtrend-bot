"""Several platforms behind the one ``VideoSource`` port.

YouTube is required: its failure (quota, bad key) fails the run as before. Bilibili is best effort — it
runs only when the config lists ``bilibili_keywords``, and a blocked request is reported as a warning.
"""
from __future__ import annotations

from datetime import datetime

from application.observer import NullObserver, Observer
from domain.models import Channel, HotSeries, VideoSnapshot
from infrastructure import bilibili_api, youtube_api

SEARCH_PAGES = 2


class MultiSource:
    def __init__(self, youtube, bilibili=None, observer: Observer | None = None) -> None:
        self._youtube = youtube
        self._bilibili = bilibili
        self._obs = observer or NullObserver()

    def collect(
        self,
        regions: tuple[str, ...],
        keywords: tuple[str, ...],
        now: datetime,
        chart_enabled: bool = True,
        window_hours: int = 48,
        bilibili_keywords: tuple[str, ...] = (),
        min_duration_sec: int = 0,
    ) -> list[VideoSnapshot]:
        videos = self._youtube.collect(regions, keywords, now, chart_enabled, window_hours, min_duration_sec)
        if self._bilibili and bilibili_keywords:
            found = self._bilibili.collect(bilibili_keywords, now, window_hours, min_duration_sec)
            self._drain_warnings()
            self._obs.info(f"Bilibili: {len(found)} video(s) from {len(bilibili_keywords)} keyword(s)")
            seen = {v.id for v in videos}
            videos += [v for v in found if v.id not in seen]
        return videos

    def search(self, query: str, now: datetime, window_hours: int) -> list[VideoSnapshot]:
        """One query on Bilibili, every length, two pages (40 videos): what a one-off search asks for."""
        if not self._bilibili:
            return []
        found = self._bilibili.collect((query,), now, window_hours, 0, pages=SEARCH_PAGES)
        self._drain_warnings()
        self._obs.info(f"Bilibili: {len(found)} video(s) for {query!r}")
        return found

    def trending(self, now: datetime) -> list[VideoSnapshot]:
        if not self._bilibili:
            return []
        found = self._bilibili.trending(now)
        self._drain_warnings()
        self._obs.info(f"Bilibili: {len(found)} video(s) from the hot lists")
        return found

    def hot_series(self, season_types: tuple[int, ...], now: datetime) -> list[HotSeries]:
        """Bilibili's live series ranking; empty without an adapter, a configured type, or an answer."""
        if not (self._bilibili and season_types):
            return []
        series = self._bilibili.series_ranking(season_types)
        self._drain_warnings()
        return series

    def video_parts(self, video_ids: list[str]) -> dict[str, list[int]]:
        """``{video id: [part seconds…]}`` for Bilibili ids (``bi_BV…``) Bilibili answered for."""
        if not self._bilibili:
            return {}
        prefix = bilibili_api.PREFIX
        wanted = {v.removeprefix(prefix): v for v in video_ids if v.startswith(prefix)}
        found = self._bilibili.part_durations(list(wanted))
        self._drain_warnings()
        return {wanted[bvid]: parts for bvid, parts in found.items()}

    def fetch_channels(self, channel_ids: list[str], now: datetime) -> list[Channel]:
        bili = [c for c in channel_ids if c.startswith(bilibili_api.PREFIX)]
        yt = [c for c in channel_ids if c.startswith(youtube_api.PREFIX)]
        out = self._youtube.fetch_channels(yt, now) if yt else []
        if bili and self._bilibili:
            out += self._bilibili.fetch_channels(bili, now)
            self._drain_warnings()
        return out

    def _drain_warnings(self) -> None:
        for message in self._bilibili.warnings:
            self._obs.warn(message)
        self._bilibili.warnings.clear()
