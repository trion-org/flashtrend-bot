"""Bilibili adapter — keyword search plus a follower-based channel baseline. Metadata only, no login.

Bilibili has no public API for this, so it reads the web endpoints the site itself calls, anonymously:

* ``x/web-interface/search/type`` — ``order=click`` with ``pubtime_begin_s/_end_s``: the most-played videos
  of a keyword inside the window (20 per page), with play, like and comment counts. Measured 2026-10-31.
* ``pgc/web/rank/list`` — the live "hot now" ranking of Chinese-animation (国创) *series*, e.g. 灵笼 第二季
  (``season_type=4``). Measured 2026-10-31: the per-category *video* rankings (``ranking/v2`` with a ``rid``
  other than 0) are frozen at Mar 2025 — every item 576+ days old — so they are not used.
* ``x/player/pagelist`` — the parts (分P) of one video with each part's length. Search reports the *sum* of
  the parts, but the player opens part 1, so a 9-hour upload can open on a 7-minute clip. Measured 2026-10-31:
  10 hot videos, totals identical to search, 4 with several parts (part 1 of 18 was 1 h 56 of 46 h).
* ``x/web-interface/card`` — a channel's ``fans``, ``archive_count`` and received likes. The endpoint that
  would give a channel's recent plays (``space/wbi/arc/search``) answers ``-352`` to anonymous callers,
  so the baseline is the follower count: a video's ratio is *views per follower*.

Its anti-bot layer answers some requests with HTTP 412 at random (the same URL passes a moment later),
so every request is retried after a wait; a keyword that stays blocked is skipped and reported, never
fatal — a blocked Bilibili must not cost the YouTube digest. No cookie is used: the repo is public and
the cookie of a personal account does not belong in GitHub Actions.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta

from domain.clock import to_vn
from domain.models import Channel, HotSeries, VideoSnapshot

PLATFORM = "bilibili"
PREFIX = "bi_"
CHANNEL_CACHE = timedelta(hours=24)
DESCRIPTION_MAX_CHARS = 500
SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
CARD_URL = "https://api.bilibili.com/x/web-interface/card"
#: Bilibili's ``duration`` search filter: 4 = longer than 60 minutes
LONG_DURATION_CODE = 4
LONG_FROM_SEC = 3600  # a minimum this long makes the search ask for ``duration=4``
SERIES_URL = "https://api.bilibili.com/pgc/web/rank/list"
PAGELIST_URL = "https://api.bilibili.com/x/player/pagelist"
BREAKER_AFTER = 3  # consecutive blocked requests after which the rest of the run stops asking
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", "Referer": "https://www.bilibili.com/"}
WAITS = (3.0, 8.0, 20.0)  # seconds before each retry of a blocked request
PAGE_SIZE = 20

_TAGS = re.compile(r"</?em\b[^>]*>")  # only the highlight Bilibili adds: a title may hold other <...>


class BilibiliUnavailable(Exception):
    """A request stayed blocked or malformed after every retry."""


def clean_title(raw: str) -> str:
    """Search results wrap the matched words in ``<em class="keyword">``; drop those tags, decode entities."""
    return html.unescape(_TAGS.sub("", raw or "")).strip()


def parse_duration(value) -> int | None:
    """``"72:22"`` / ``"1:02:03"`` → seconds; None when missing or unparseable."""
    try:
        parts = [int(p) for p in str(value).split(":")]  # "72:22", "1:02:03" — or plain seconds (rankings)
    except ValueError:
        return None
    if not parts or len(parts) > 3:
        return None
    total = 0
    for p in parts:
        total = total * 60 + p
    return total or None


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _https(url: str | None) -> str | None:
    return ("https:" + url) if url and url.startswith("//") else (url or None)


def http_json(url: str) -> dict:
    """GET ``url`` → decoded JSON. Raises ``urllib.error.URLError`` / ``ValueError`` on failure."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as resp:
        return json.load(resp)


class BilibiliSource:
    """Keyword search and channel baselines for Bilibili. ``fetch`` and ``sleep`` are injectable."""

    def __init__(
        self,
        fetch: Callable[[str], dict] = http_json,
        sleep: Callable[[float], None] = time.sleep,
        waits: tuple[float, ...] = WAITS,
        pause: float = 1.0,
    ) -> None:
        self._fetch = fetch
        self._sleep = sleep
        self._waits = waits
        self._pause = pause  # between two requests, so a burst does not look like a bot
        self.warnings: list[str] = []
        self._blocked_in_a_row = 0  # circuit breaker: a blocked runner would burn minutes on retries

    # ----------------------------------------------------------------- search

    def collect(self, keywords: tuple[str, ...], now: datetime, window_hours: int,
                min_duration_sec: int = 0) -> list[VideoSnapshot]:
        """Most-played videos per keyword. With ``min_duration_sec`` of an hour or more the search itself asks
        for ``duration=4`` (over 60 minutes), so its results are the long ones, and reads 2 pages."""
        found: dict[str, VideoSnapshot] = {}
        long_only = min_duration_sec >= LONG_FROM_SEC
        end = int(now.timestamp())
        begin = int((now - timedelta(hours=window_hours)).timestamp())
        requests = [(keyword, page) for keyword in keywords for page in range(1, 3 if long_only else 2)]
        for i, (keyword, page) in enumerate(requests):
            if i:
                self._sleep(self._pause)
            params = {"search_type": "video", "keyword": keyword, "order": "click", "page": page,
                      "pubtime_begin_s": begin, "pubtime_end_s": end}
            if long_only:
                params["duration"] = LONG_DURATION_CODE
            try:
                data = self._get(SEARCH_URL, params)
            except BilibiliUnavailable as exc:
                self.warnings.append(f"Bilibili search {keyword!r} skipped: {exc}")
                if self._tripped():
                    break
                continue
            for item in (data.get("data") or {}).get("result") or []:
                video = self._parse(item, now, keyword)
                if video:
                    found.setdefault(video.id, video)
        return list(found.values())

    def part_durations(self, bvids: list[str]) -> dict[str, list[int]]:
        """{bvid: [seconds of part 1, part 2, …]} for the videos Bilibili answered for (others: absent)."""
        out: dict[str, list[int]] = {}
        for i, bvid in enumerate(bvids):
            if i:
                self._sleep(self._pause)
            try:
                data = self._get(PAGELIST_URL, {"bvid": bvid})
            except BilibiliUnavailable as exc:
                self.warnings.append(f"Bilibili parts of {bvid} skipped: {exc}")
                if self._tripped():
                    break
                continue
            parts = [_int(p.get("duration")) for p in data.get("data") or [] if isinstance(p, dict)]
            if parts and sum(parts) > 0:
                out[bvid] = parts
        return out

    def series_ranking(self, season_types: tuple[int, ...], limit: int = 10) -> list[HotSeries]:
        """The live "hot now" series ranking (``season_type`` 4 = 国创), most-watched first."""
        out: list[HotSeries] = []
        for i, season_type in enumerate(season_types):
            if i:
                self._sleep(self._pause)
            try:
                data = self._get(SERIES_URL, {"day": 3, "season_type": season_type})
            except BilibiliUnavailable as exc:
                self.warnings.append(f"Bilibili series ranking {season_type} skipped: {exc}")
                if self._tripped():
                    break
                continue
            for item in ((data.get("result") or data.get("data") or {}).get("list") or [])[:limit]:
                series = self._parse_series(item)
                if series:
                    out.append(series)
        return out

    @staticmethod
    def _parse_series(item: dict) -> HotSeries | None:
        season_id, title = item.get("season_id"), clean_title(item.get("title", ""))
        url = item.get("url") or (f"https://www.bilibili.com/bangumi/play/ss{season_id}" if season_id else "")
        if not season_id or not title or not url.startswith("https://"):
            return None
        return HotSeries(
            rank=_int(item.get("rank")) or 1,
            season_id=int(season_id),
            title=title,
            url=url,
            views=_int((item.get("stat") or {}).get("view")),
            rating=item.get("rating") or None,
            episodes=(item.get("new_ep") or {}).get("index_show") or None,
        )

    def _tripped(self) -> bool:
        """True once ``BREAKER_AFTER`` requests in a row stayed blocked: stop asking for this run."""
        if self._blocked_in_a_row >= BREAKER_AFTER:
            self.warnings.append(
                f"Bilibili blocked {BREAKER_AFTER} requests in a row: the rest of this run skips it"
            )
            return True
        return False

    @staticmethod
    def _parse(item: dict, now: datetime, tag: str) -> VideoSnapshot | None:
        bvid, mid, pubdate = item.get("bvid"), item.get("mid"), item.get("pubdate")
        if not bvid or not mid or not pubdate:
            return None
        return VideoSnapshot(
            id=PREFIX + bvid,
            platform=PLATFORM,
            native_id=bvid,
            url=f"https://www.bilibili.com/video/{bvid}",
            title=clean_title(item.get("title", "")),
            description=clean_title(item.get("description", ""))[:DESCRIPTION_MAX_CHARS],
            published_at=to_vn(datetime.fromtimestamp(int(pubdate), tz=now.tzinfo)),
            channel_id=PREFIX + str(mid),
            duration_sec=parse_duration(item.get("duration")),
            thumbnail_url=_https(item.get("pic")),
            views=_int(item.get("play")),
            likes=_int(item.get("like")),
            comments=_int(item.get("review")),
            captured_at=to_vn(now),
            query_tag=tag,
        )

    # --------------------------------------------------------------- channels

    def fetch_channels(self, channel_ids: list[str], now: datetime) -> list[Channel]:
        out: list[Channel] = []
        for i, cid in enumerate(channel_ids):
            if i:
                self._sleep(self._pause)
            mid = cid.removeprefix(PREFIX)
            if self._blocked_in_a_row >= BREAKER_AFTER:
                break  # already reported when the breaker tripped
            try:
                data = self._get(CARD_URL, {"mid": mid, "photo": "false"})
            except BilibiliUnavailable as exc:
                self.warnings.append(f"Bilibili channel {mid} skipped: {exc}")
                if self._tripped():
                    break
                continue
            body = data.get("data") or {}
            card = body.get("card") or {}
            fans = _int(card.get("fans"))
            out.append(
                Channel(
                    id=cid,
                    platform=PLATFORM,
                    native_id=mid,
                    title=card.get("name") or mid,
                    subscriber_count=fans or None,
                    video_count=_int(body.get("archive_count")) or None,
                    channel_avg_views=float(fans),  # followers as the baseline: ratio = views per follower
                    fetched_at=now,
                    stale_after=now + CHANNEL_CACHE,
                )
            )
        return out

    # ------------------------------------------------------------------- http

    def _get(self, url: str, params: dict) -> dict:
        """GET with retries on the anti-bot answers (HTTP 412, ``code`` -412/-352) and network errors."""
        if self._blocked_in_a_row >= BREAKER_AFTER:
            raise BilibiliUnavailable("circuit open")
        full = f"{url}?{urllib.parse.urlencode(params)}"
        last = "no attempt"
        for wait in (*self._waits, None):
            try:
                data = self._fetch(full)
                code = data.get("code")
                if code == 0:
                    self._blocked_in_a_row = 0
                    return data
                last = f"code {code} {data.get('message', '')}".strip()
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                last = type(exc).__name__
            if wait is not None:
                self._sleep(wait)
        self._blocked_in_a_row += 1
        raise BilibiliUnavailable(last)
