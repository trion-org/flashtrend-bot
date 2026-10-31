"""YouTube Data API v3 adapter (A1 chart · A2 keyword search · A3 channel baselines).

Quota (docs/01): ``videos.list`` and ``channels.list`` cost 1 unit, ``search.list`` costs 100.
Only metadata is read — nothing is downloaded.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from googleapiclient.errors import HttpError

from domain import errors as E
from domain.clock import to_vn
from domain.errors import FlashTrendError
from domain.models import Channel, VideoSnapshot
from infrastructure.timeutil import iso, parse_ts

PLATFORM = "youtube"
PREFIX = "yt_"
CHANNEL_CACHE = timedelta(hours=24)
DESCRIPTION_MAX_CHARS = 500
BATCH = 50
LONG_FROM_SEC = 1200  # a minimum this long makes the search ask for ``videoDuration=long`` (over 20 min)

_DURATION = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
_AUTH_REASONS = {"keyInvalid", "forbidden", "accessNotConfigured", "ipRefererBlocked"}


def parse_duration(value: str | None) -> int | None:
    """ISO-8601 ``PT1H2M3S`` → seconds (None when missing/unparseable, e.g. live streams ``P0D``)."""
    if not value:
        return None
    m = _DURATION.match(value)
    if not m:
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + s
    return total or None  # P0D (live/premiere) is unknown, not a zero-second video


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def map_http_error(exc: HttpError) -> FlashTrendError:
    """403 quotaExceeded → YT_QUOTA; bad/forbidden key → YT_AUTH; anything else is unexpected."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    reason, message = "", str(exc)
    try:
        body = json.loads(exc.content.decode("utf-8")) if exc.content else {}
        err = body.get("error", {})
        message = err.get("message", message)
        errors = err.get("errors") or [{}]
        reason = errors[0].get("reason", "")
    except (ValueError, AttributeError):
        pass
    details = {"status": status, "reason": reason}
    if reason in _QUOTA_REASONS:
        return FlashTrendError(E.YT_QUOTA, "YouTube Data API quota exceeded", details)
    if reason in _AUTH_REASONS or status in (401, 403):
        return FlashTrendError(E.YT_AUTH, f"YouTube API rejected the key: {message}", details)
    return FlashTrendError(E.UNEXPECTED, f"YouTube API error {status}: {message}", details)


class YouTubeSource:
    """Implements ``VideoSource``. ``client`` is a ``googleapiclient`` resource (injectable)."""

    def __init__(
        self,
        client,
        chart_max: int = 50,
        search_max: int = 25,
    ) -> None:
        self._yt = client
        self._chart_max = chart_max
        self._search_max = search_max

    @classmethod
    def from_api_key(cls, api_key: str, **kwargs) -> YouTubeSource:
        from googleapiclient.discovery import build

        return cls(build("youtube", "v3", developerKey=api_key, cache_discovery=False), **kwargs)

    # ------------------------------------------------------------- VideoSource

    def collect(
        self,
        regions: tuple[str, ...],
        keywords: tuple[str, ...],
        now: datetime,
        chart_enabled: bool = True,
        window_hours: int = 48,
        min_duration_sec: int = 0,
    ) -> list[VideoSnapshot]:
        found: dict[str, VideoSnapshot] = {}
        if chart_enabled:
            for region in regions:
                for video in self._chart(region, now):
                    found.setdefault(video.id, video)
        search_region = regions[0] if regions else None
        for keyword in keywords:
            ids = self._search(keyword, search_region, now, timedelta(hours=window_hours),
                               min_duration_sec >= LONG_FROM_SEC)
            for video in self._videos(ids, now, tag=keyword):
                found.setdefault(video.id, video)
        return list(found.values())

    def fetch_channels(self, channel_ids: list[str], now: datetime) -> list[Channel]:
        out: list[Channel] = []
        native = [c.removeprefix(PREFIX) for c in channel_ids]
        for i in range(0, len(native), BATCH):
            chunk = native[i : i + BATCH]
            resp = self._execute(
                self._yt.channels().list(
                    part="snippet,statistics", id=",".join(chunk), maxResults=len(chunk)
                )
            )
            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                views, count = _int(stats.get("viewCount")), _int(stats.get("videoCount"))
                hidden = stats.get("hiddenSubscriberCount")
                out.append(
                    Channel(
                        id=PREFIX + item["id"],
                        platform=PLATFORM,
                        native_id=item["id"],
                        title=item.get("snippet", {}).get("title", item["id"]),
                        subscriber_count=None if hidden else _int(stats.get("subscriberCount")),
                        video_count=count or None,
                        channel_avg_views=(views / count) if count and views else 0.0,
                        fetched_at=now,
                        stale_after=now + CHANNEL_CACHE,
                    )
                )
        return out

    # ---------------------------------------------------------------- queries

    def _chart(self, region: str, now: datetime) -> list[VideoSnapshot]:
        resp = self._execute(
            self._yt.videos().list(
                part="snippet,statistics,contentDetails",
                chart="mostPopular",
                regionCode=region,
                maxResults=self._chart_max,
            )
        )
        return [v for v in (self._parse(i, now, "chart") for i in resp.get("items", [])) if v]

    def _search(
        self, keyword: str, region: str | None, now: datetime, window: timedelta, long_only: bool = False
    ) -> list[str]:
        params = {
            "part": "id",
            "q": keyword,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": iso(now - window),
            "maxResults": self._search_max,
        }
        if region:
            params["regionCode"] = region
        if long_only:
            params["videoDuration"] = "long"  # over 20 minutes: the only length filter the API has
        resp = self._execute(self._yt.search().list(**params))
        return [i["id"]["videoId"] for i in resp.get("items", []) if i.get("id", {}).get("videoId")]

    def _videos(self, ids: list[str], now: datetime, tag: str) -> list[VideoSnapshot]:
        out: list[VideoSnapshot] = []
        for i in range(0, len(ids), BATCH):
            chunk = ids[i : i + BATCH]
            resp = self._execute(
                self._yt.videos().list(
                    part="snippet,statistics,contentDetails", id=",".join(chunk), maxResults=len(chunk)
                )
            )
            out.extend(v for v in (self._parse(it, now, tag) for it in resp.get("items", [])) if v)
        return out

    def _execute(self, request) -> dict:
        try:
            return request.execute()
        except HttpError as exc:
            raise map_http_error(exc) from exc

    @staticmethod
    def _parse(item: dict, now: datetime, tag: str) -> VideoSnapshot | None:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        vid = item.get("id")
        if not vid or not snippet.get("publishedAt") or not snippet.get("channelId"):
            return None
        if snippet.get("liveBroadcastContent") in ("live", "upcoming"):
            return None  # a running/scheduled stream has no settled view count
        thumbs = snippet.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        published = parse_ts(snippet["publishedAt"])
        return VideoSnapshot(
            id=PREFIX + vid,
            platform=PLATFORM,
            native_id=vid,
            url=f"https://www.youtube.com/watch?v={vid}",
            title=snippet.get("title", "").strip(),
            description=snippet.get("description", "")[:DESCRIPTION_MAX_CHARS],
            published_at=published,
            channel_id=PREFIX + snippet["channelId"],
            duration_sec=parse_duration(item.get("contentDetails", {}).get("duration")),
            thumbnail_url=thumb,
            views=_int(stats.get("viewCount")),
            likes=_int(stats.get("likeCount")),
            comments=_int(stats.get("commentCount")),
            captured_at=to_vn(now),
            query_tag=tag,
        )
