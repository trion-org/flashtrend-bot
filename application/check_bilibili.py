"""Smoke test of the Bilibili adapter from wherever it runs (a GitHub runner may be blocked)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from application.observer import Observer

KEYWORD = "修仙动画"
WINDOW_HOURS = 168


class CheckBilibili:
    def __init__(self, source, observer: Observer, clock: Callable[[], datetime]) -> None:
        self._source, self._obs, self._clock = source, observer, clock

    def run(self) -> bool:
        """One search and one channel card; True when both answered."""
        now = self._clock()
        videos = self._source.collect((KEYWORD,), now, WINDOW_HOURS)
        channels = self._source.fetch_channels([videos[0].channel_id], now) if videos else []
        for message in self._source.warnings:
            self._obs.warn(message)
        self._obs.info(
            f"Bilibili check: {len(videos)} video(s) for {KEYWORD!r} in {WINDOW_HOURS} h, "
            f"{len(channels)} channel card(s)"
        )
        return bool(videos and channels)
