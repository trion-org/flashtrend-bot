"""Several platforms behind the one ``VideoSource`` port.

YouTube is required: its failure (quota, bad key) fails the run as before. Bilibili is best effort — it
runs only when the config lists ``bilibili_keywords``, and a blocked request is reported as a warning.
"""
from __future__ import annotations

from datetime import datetime

from application.observer import NullObserver, Observer
from domain.models import Channel, VideoSnapshot
from infrastructure import bilibili_api, youtube_api


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
    ) -> list[VideoSnapshot]:
        videos = self._youtube.collect(regions, keywords, now, chart_enabled, window_hours)
        if self._bilibili and bilibili_keywords:
            found = self._bilibili.collect(bilibili_keywords, now, window_hours)
            self._drain_warnings()
            self._obs.info(f"Bilibili: {len(found)} video(s) from {len(bilibili_keywords)} keyword(s)")
            seen = {v.id for v in videos}
            videos = videos + [v for v in found if v.id not in seen]
        return videos

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
