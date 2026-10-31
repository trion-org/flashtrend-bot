"""Supabase (PostgREST) adapter for ``DigestStore``. Uses the ``service_role`` key — Actions only.

Rules from docs/03: list columns explicitly (no ``select *`` except the one-row config), never pull
vectors beyond this run's few outliers, never write estfstudio's tables (``estf_*``, ``feedback``,
``ideas.status``). Server-side helpers (cosine search, TTL cleanup, db size) are the SQL functions
in ``sql/03_functions.sql`` because PostgREST cannot express ``<=>`` or multi-table deletes.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import TypeVar

from application.ports import RunPoint
from domain import errors as E
from domain.clock import now_vn
from domain.errors import FlashTrendError
from domain.models import (
    AppConfig,
    Candidate,
    Channel,
    HotVideo,
    Idea,
    Media,
    PreviousSnapshot,
    RunRequest,
    RunStats,
    VideoSnapshot,
)
from infrastructure.timeutil import iso, parse_ts

T = TypeVar("T")
WRITE_CHUNK = 500
READ_CHUNK = 50  # PostgREST caps a response at 1000 rows; 50 ids × a few snapshots stays below it
SNAPSHOT_LOOKBACK = timedelta(days=3)


def _chunks(items: list[T], size: int) -> Iterable[list[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


class SupabaseStore:
    def __init__(self, client) -> None:
        self._db = client

    @classmethod
    def connect(cls, url: str, service_role_key: str) -> SupabaseStore:
        from supabase import create_client

        return cls(create_client(url, service_role_key))

    # --------------------------------------------------------------- plumbing

    def _write(self, what: str, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except FlashTrendError:
            raise
        except Exception as exc:  # noqa: BLE001 - PostgREST/httpx errors vary
            raise FlashTrendError(
                E.DB_WRITE, f"{what}: {type(exc).__name__}: {exc}", {"operation": what}
            ) from exc

    def _rows(self, response) -> list[dict]:
        return list(response.data or [])

    # ----------------------------------------------------------------- config

    def get_app_config(self) -> AppConfig:
        rows = self._write(
            "read app_config",
            lambda: self._rows(self._db.table("app_config").select("*").eq("id", 1).execute()),
        )
        if not rows:
            raise FlashTrendError(
                E.SCHEMA_MISMATCH,
                "app_config has no row: run sql/04_seed_app_config.sql",
                {"table": "app_config"},
            )
        r = rows[0]
        d = AppConfig()
        return AppConfig(
            schema_version=int(r.get("schema_version", d.schema_version)),
            regions=tuple(r.get("regions") or d.regions),
            keywords=tuple(r.get("keywords") or ()),
            z_threshold=float(r.get("z_threshold", d.z_threshold)),
            relaxed_z_threshold=float(r.get("relaxed_z_threshold", d.relaxed_z_threshold)),
            cosine_threshold=float(r.get("cosine_threshold", d.cosine_threshold)),
            history_cosine_threshold=float(
                r.get("history_cosine_threshold", d.history_cosine_threshold)
            ),
            decay_lambda=float(r.get("decay_lambda", d.decay_lambda)),
            engagement_like_w=float(r.get("engagement_like_w", d.engagement_like_w)),
            engagement_comment_w=float(r.get("engagement_comment_w", d.engagement_comment_w)),
            bayes_c=int(r.get("bayes_c", d.bayes_c)),
            min_cohort_n=int(r.get("min_cohort_n", d.min_cohort_n)),
            snapshot_ttl_days=int(r.get("snapshot_ttl_days", d.snapshot_ttl_days)),
            llm_enabled=bool(r.get("llm_enabled", d.llm_enabled)),
            chart_enabled=bool(r.get("chart_enabled", d.chart_enabled)),
            search_window_hours=int(r.get("search_window_hours", d.search_window_hours)),
            bilibili_keywords=tuple(r.get("bilibili_keywords") or ()),
            bilibili_series_types=tuple(int(x) for x in (r.get("bilibili_series_types") or ())),
            niche_terms=tuple(r.get("niche_terms") or ()),
            niche_exclude_terms=tuple(r.get("niche_exclude_terms") or ()),
            niche_only=bool(r.get("niche_only", d.niche_only)),
            min_duration_sec=int(r.get("min_duration_sec", d.min_duration_sec)),
            niche_boost=float(r.get("niche_boost", d.niche_boost)),
            youtube_search_every_hours=int(r.get("youtube_search_every_hours", d.youtube_search_every_hours)),
            analysis_every_hours=int(r.get("analysis_every_hours", d.analysis_every_hours)),
        )

    # ------------------------------------------------------------------- runs

    def open_run(
        self, run_id: str, trigger: str, git_sha: str, region: str, started_at: datetime,
        request: RunRequest | None = None, query_zh: str | None = None,
    ) -> None:
        row = {
            "id": run_id,
            "schema_version": 1,
            "trigger": trigger,
            "git_sha": git_sha,
            "region": region,
            "started_at": iso(started_at),
            "status": "running",
        }
        if request is not None:  # sql/09; the hourly digest keeps the column defaults
            row |= {"mode": request.mode, "query": request.query, "query_zh": query_zh,
                    "request_id": request.request_id}
        self._write("open run", lambda: self._db.table("runs").insert(row).execute())

    def finish_run(
        self,
        run_id: str,
        status: str,
        finished_at: datetime,
        stats: RunStats,
        error: dict | None,
        chart_media_id: str | None,
    ) -> None:
        cohort = stats.cohort
        row = {
            "status": status,
            "finished_at": iso(finished_at),
            "error": error,
            "collected": stats.collected,
            "scored": stats.scored,
            "outliers": stats.outliers,
            "ideas_count": stats.ideas_count,
            "cohort_n": cohort.n if cohort else None,
            "cohort_mu_ratio": cohort.mu_ratio if cohort else None,
            "cohort_sigma_ratio": cohort.sigma_ratio if cohort else None,
            "cohort_median_engagement": cohort.median_engagement if cohort else None,
            "z_threshold_used": cohort.z_threshold_used if cohort else None,
            "duration_ms": stats.duration_ms,
            "chart_media_id": chart_media_id,
        }
        self._write(
            "close run", lambda: self._db.table("runs").update(row).eq("id", run_id).execute()
        )

    # --------------------------------------------------------------- channels

    def get_channels(self, channel_ids: list[str]) -> dict[str, Channel]:
        out: dict[str, Channel] = {}
        cols = (
            "id,platform,native_id,title,subscriber_count,video_count,channel_avg_views,"
            "fetched_at,stale_after"
        )
        for chunk in _chunks(channel_ids, 100):
            rows = self._write(
                "read channels",
                lambda c=chunk: self._rows(
                    self._db.table("channels").select(cols).in_("id", c).execute()
                ),
            )
            for r in rows:
                out[r["id"]] = Channel(
                    id=r["id"],
                    platform=r["platform"],
                    native_id=r["native_id"],
                    title=r["title"],
                    subscriber_count=r.get("subscriber_count"),
                    video_count=r.get("video_count"),
                    channel_avg_views=float(r["channel_avg_views"]),
                    fetched_at=parse_ts(r["fetched_at"]),
                    stale_after=parse_ts(r["stale_after"]),
                )
        return out

    def upsert_channels(self, channels: list[Channel]) -> None:
        rows = [
            {
                "id": c.id,
                "platform": c.platform,
                "native_id": c.native_id,
                "title": c.title,
                "subscriber_count": c.subscriber_count,
                "video_count": c.video_count,
                "channel_avg_views": c.channel_avg_views,
                "fetched_at": iso(c.fetched_at),
                "stale_after": iso(c.stale_after),
            }
            for c in channels
        ]
        for chunk in _chunks(rows, WRITE_CHUNK):
            self._write(
                "upsert channels",
                lambda c=chunk: self._db.table("channels").upsert(c, on_conflict="id").execute(),
            )

    # ----------------------------------------------------------------- videos

    def upsert_videos(self, videos: list[VideoSnapshot], run_id: str, now: datetime) -> None:
        """New rows get ``first_seen_at = now``; existing rows keep the value already stored.

        PostgREST checks NOT NULL on the proposed row *before* resolving the conflict, so an
        upsert cannot simply omit ``first_seen_at``: the stored value is read and sent back as is.
        """
        first_seen: dict[str, str] = {}
        for chunk in _chunks([v.id for v in videos], 100):
            rows = self._write(
                "read videos",
                lambda c=chunk: self._rows(
                    self._db.table("videos").select("id,first_seen_at").in_("id", c).execute()
                ),
            )
            first_seen.update({r["id"]: r["first_seen_at"] for r in rows})

        def row(v: VideoSnapshot) -> dict:
            return {
                "id": v.id,
                "platform": v.platform,
                "native_id": v.native_id,
                "url": v.url,
                "title": v.title,
                "description": v.description,
                "published_at": iso(v.published_at),
                "channel_id": v.channel_id,
                "duration_sec": v.duration_sec,
                "thumbnail_url": v.thumbnail_url,
                "last_views": v.views,
                "last_likes": v.likes,
                "last_comments": v.comments,
                "first_seen_at": first_seen.get(v.id) or iso(now),
                "last_seen_at": iso(now),
                "last_run_id": run_id,
            }

        rows = [row(v) for v in videos]
        for chunk in _chunks(rows, WRITE_CHUNK):
            self._write(
                "upsert videos",
                lambda c=chunk: self._db.table("videos").upsert(c, on_conflict="id").execute(),
            )

    def insert_snapshots(self, videos: list[VideoSnapshot], run_id: str, ttl_days: int) -> None:
        rows = [
            {
                "video_id": v.id,
                "run_id": run_id,
                "captured_at": iso(v.captured_at),
                "views": v.views,
                "likes": v.likes,
                "comments": v.comments,
                "expire_at": iso(v.captured_at + timedelta(days=ttl_days)),
            }
            for v in videos
        ]
        for chunk in _chunks(rows, WRITE_CHUNK):
            self._write(
                "insert snapshots",
                lambda c=chunk: self._db.table("snapshots")
                .upsert(c, on_conflict="video_id,run_id")
                .execute(),
            )

    def previous_snapshots(
        self, video_ids: list[str], before: datetime, limit: int
    ) -> dict[str, list[PreviousSnapshot]]:
        out: dict[str, list[PreviousSnapshot]] = {}
        since = iso(before - SNAPSHOT_LOOKBACK)
        for chunk in _chunks(video_ids, READ_CHUNK):
            rows = self._write(
                "read snapshots",
                lambda c=chunk: self._rows(
                    self._db.table("snapshots")
                    .select("video_id,views,captured_at")
                    .in_("video_id", c)
                    .lt("captured_at", iso(before))
                    .gte("captured_at", since)
                    .order("captured_at", desc=True)
                    .execute()
                ),
            )
            for r in rows:
                bucket = out.setdefault(r["video_id"], [])
                if len(bucket) < limit:
                    bucket.append(PreviousSnapshot(int(r["views"]), parse_ts(r["captured_at"])))
        return out

    # ------------------------------------------------------------- candidates

    def insert_candidates(self, run_id: str, candidates: list[Candidate], ttl_days: int) -> None:
        rows = [
            {
                "run_id": run_id,
                "video_id": c.video.id,
                "platform": c.video.platform,
                "title": c.video.title,
                "url": c.video.url,
                "channel_id": c.video.channel_id,
                "views": c.video.views,
                "likes": c.video.likes,
                "comments": c.video.comments,
                "age_hours": c.video.age_hours,
                "channel_avg_views": c.channel_avg_views,
                "performance_ratio": c.performance_ratio,
                "z_score": c.z_score,
                "engagement": c.engagement,
                "time_decay": c.time_decay,
                "velocity": c.velocity,
                "acceleration": c.acceleration,
                "early_flag": c.early_flag,
                "viral_score": c.viral_score,
                "passed_z": c.passed_z,
                "query_tag": c.video.query_tag,
                "expire_at": iso(c.video.captured_at + timedelta(days=ttl_days)),
            }
            for c in candidates
        ]
        for chunk in _chunks(rows, WRITE_CHUNK):
            self._write(
                "insert candidates",
                lambda c=chunk: self._db.table("candidates")
                .upsert(c, on_conflict="run_id,video_id")
                .execute(),
            )

    # ------------------------------------------------------------- embeddings

    def get_embeddings(self, video_ids: list[str]) -> dict[str, tuple[str, list[float]]]:
        out: dict[str, tuple[str, list[float]]] = {}
        for chunk in _chunks(video_ids, READ_CHUNK):
            rows = self._write(
                "read embeddings",
                lambda c=chunk: self._rows(
                    self._db.table("embeddings")
                    .select("video_id,text_hash,embedding")
                    .in_("video_id", c)
                    .execute()
                ),
            )
            for r in rows:
                vec = r["embedding"]
                if isinstance(vec, str):  # pgvector comes back as '[0.1,0.2,…]'
                    vec = json.loads(vec)
                out[r["video_id"]] = (r["text_hash"], [float(x) for x in vec])
        return out

    def upsert_embeddings(
        self, rows: list[tuple[str, str, str, list[float]]], now: datetime
    ) -> None:
        payload = [
            {
                "video_id": vid,
                "model": "all-MiniLM-L6-v2",
                "dim": 384,
                "text_hash": text_hash,
                "source": source,
                "embedding": _vector_literal(vec),
                "updated_at": iso(now),
            }
            for vid, text_hash, source, vec in rows
        ]
        for chunk in _chunks(payload, 100):
            self._write(
                "upsert embeddings",
                lambda c=chunk: self._db.table("embeddings")
                .upsert(c, on_conflict="video_id")
                .execute(),
            )

    def nearest_history(
        self, vector: list[float], days: int, exclude_ids: list[str]
    ) -> float | None:
        """C3, computed server-side so no vector is pulled back (``flashtrend_max_cosine``)."""
        resp = self._write(
            "history cosine",
            lambda: self._db.rpc(
                "flashtrend_max_cosine",
                {"query": _vector_literal(vector), "p_days": days, "exclude_ids": exclude_ids},
            ).execute(),
        )
        value = resp.data
        return None if value is None else float(value)

    def proposed_video_ids(self, days: int) -> set[str]:
        since = iso(now_vn() - timedelta(days=days))
        rows = self._write(
            "read proposed ideas",
            lambda: self._rows(
                self._db.table("ideas").select("video_id").gte("created_at", since).execute()
            ),
        )
        return {r["video_id"] for r in rows}

    # ------------------------------------------------------------------ ideas

    def insert_ideas(self, run_id: str, ideas: list[Idea]) -> None:
        rows = []
        for i in ideas:
            c, v = i.candidate, i.candidate.video
            rows.append(
                {
                    "run_id": run_id,
                    "video_id": v.id,
                    "platform": v.platform,
                    "title": v.title,
                    "url": v.url,
                    "published_at": iso(v.published_at),
                    "views": v.views,
                    "likes": v.likes,
                    "comments": v.comments,
                    "channel_title": i.channel_title,
                    "channel_id": v.channel_id,
                    "channel_avg_views": c.channel_avg_views,
                    "performance_ratio": c.performance_ratio,
                    "z_score": c.z_score,
                    "engagement": c.engagement,
                    "time_decay": c.time_decay,
                    "viral_score": c.viral_score,
                    "duplicates_count": i.duplicates_count,
                    "novelty_score": i.novelty_score,
                    "cluster_id": i.cluster_id,
                    "llm": i.llm,
                }
            )
        # plain insert: ``status`` belongs to estfstudio and must never be reset by an upsert
        self._write("insert ideas", lambda: self._db.table("ideas").insert(rows).execute())

    def update_idea_llm(self, run_id: str, video_id: str, llm: dict) -> None:
        self._write(
            "update idea llm",
            lambda: self._db.table("ideas")
            .update({"llm": llm})
            .eq("run_id", run_id)
            .eq("video_id", video_id)
            .execute(),
        )

    # ------------------------------------------------------------------ media

    _MEDIA_COLS = "id,owner,kind,url,host,sha256,bytes,width,height,video_id,run_id"

    # ------------------------------------------------------------ hot videos

    def insert_hot_videos(self, run_id: str, rows: list[HotVideo]) -> None:
        payload = [
            {
                "run_id": run_id, "kind": h.kind, "rank": h.rank, "video_id": h.video_id,
                "platform": h.platform, "title": h.title, "url": h.url, "channel_title": h.channel_title,
                "views": h.views, "duration_sec": h.duration_sec,
                "published_at": iso(h.published_at) if h.published_at else None, "niche": h.niche,
                "viral_score": h.viral_score, "parts": h.parts, "first_part_sec": h.first_part_sec,
                "title_vi": h.title_vi,
            }
            for h in rows
        ]
        self._write("insert hot videos", lambda: self._db.table("hot_videos").insert(payload).execute())

    def get_titles_vi(self, title_hashes: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for chunk in _chunks(title_hashes, READ_CHUNK):
            rows = self._write(
                "read title translations",
                lambda c=chunk: self._rows(
                    self._db.table("titles_vi").select("title_hash,title_vi").in_("title_hash", c).execute()
                ),
            )
            out.update({r["title_hash"]: r["title_vi"] for r in rows if r.get("title_vi")})
        return out

    def upsert_titles_vi(self, rows: list[tuple[str, str, str]]) -> None:
        payload = [{"title_hash": h, "title": t, "title_vi": vi} for h, t, vi in rows]
        for chunk in _chunks(payload, WRITE_CHUNK):
            self._write(
                "store title translations",
                lambda c=chunk: self._db.table("titles_vi").upsert(c, on_conflict="title_hash").execute(),
            )

    def recent_runs(self, limit: int) -> list[RunPoint]:
        rows = self._write(
            "read recent runs",
            lambda: self._rows(
                self._db.table("runs").select("started_at,collected,outliers,ideas_count")
                .eq("mode", "digest").not_.is_("finished_at", "null")
                .order("started_at", desc=True).limit(limit).execute()
            ),
        )
        return [
            RunPoint(parse_ts(r["started_at"]), int(r["collected"] or 0), int(r["outliers"] or 0),
                     int(r["ideas_count"] or 0))
            for r in reversed(rows)
        ]

    def find_media(self, sha256: str) -> Media | None:
        rows = self._write(
            "find media",
            lambda: self._rows(
                self._db.table("media").select(self._MEDIA_COLS).eq("sha256", sha256).execute()
            ),
        )
        if not rows:
            return None
        r = rows[0]
        return Media(
            id=r["id"], owner=r["owner"], kind=r["kind"], url=r["url"], host=r["host"],
            sha256=r["sha256"], bytes=int(r["bytes"]), width=r.get("width"),
            height=r.get("height"), video_id=r.get("video_id"), run_id=r.get("run_id"),
        )

    def insert_media(self, media: Media) -> None:
        row = {
            "id": media.id, "owner": media.owner, "kind": media.kind, "url": media.url,
            "host": media.host, "sha256": media.sha256, "bytes": media.bytes,
            "width": media.width, "height": media.height, "video_id": media.video_id,
            "run_id": media.run_id,
        }
        if media.caption is not None:  # columns exist only after sql/07; plain media never sends them
            row["caption"] = media.caption
        if media.position is not None:
            row["position"] = media.position
        self._write("insert media", lambda: self._db.table("media").insert(row).execute())

    def list_media(self) -> list[Media]:
        rows = self._write(
            "list media",
            lambda: self._rows(self._db.table("media").select(self._MEDIA_COLS).execute()),
        )
        return [
            Media(
                id=r["id"], owner=r["owner"], kind=r["kind"], url=r["url"], host=r["host"],
                sha256=r["sha256"], bytes=int(r["bytes"]), width=r.get("width"),
                height=r.get("height"), video_id=r.get("video_id"), run_id=r.get("run_id"),
            )
            for r in rows
        ]

    def set_media_alive(self, media_id: str, alive: bool, checked_at: datetime) -> None:
        self._write(
            "update media",
            lambda: self._db.table("media")
            .update({"alive": alive, "checked_at": iso(checked_at)})
            .eq("id", media_id)
            .execute(),
        )

    # ------------------------------------------------------------- housekeeping

    def cleanup(self, ttl_days: int, embeddings_ttl_days: int) -> dict[str, int]:
        resp = self._write(
            "ttl cleanup",
            lambda: self._db.rpc(
                "flashtrend_cleanup",
                {"p_ttl_days": ttl_days, "p_embeddings_ttl_days": embeddings_ttl_days},
            ).execute(),
        )
        return dict(resp.data or {})

    def db_size_bytes(self) -> int | None:
        try:
            resp = self._db.rpc("flashtrend_db_size", {}).execute()
            return None if resp.data is None else int(resp.data)
        except Exception:  # noqa: BLE001 - optional metric; the function may not be installed yet
            return None
