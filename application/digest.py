"""RunDigest — one FlashTrend run (docs/01 five layers, docs/03 write order w1–w7).

Collect → L1 Z-Score → L2 cosine dedup → ideas (+ image) → L3 Gemini → TTL cleanup.
``runs.status`` is ``ok`` only when every idea has a schema-valid ``llm``; any failure after L2
still keeps the ``candidates``/``ideas`` (``llm = null``) and marks the run ``error``.
"""
from __future__ import annotations

import hashlib
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from application.observer import NullObserver, Observer
from application.ports import (
    ChartRenderer,
    DigestStore,
    Embedder,
    IdeaBrief,
    IdeaWriter,
    ImageHost,
    VideoSource,
)
from domain import errors as E
from domain import scoring
from domain.clock import now_vn
from domain.dedup import greedy_clusters, novelty_score
from domain.errors import FlashTrendError
from domain.llm_contract import LlmSchemaError, validate_llm
from domain.models import (
    MAX_IMAGE_BYTES,
    SUPPORTED_SCHEMA_VERSION,
    AppConfig,
    Candidate,
    Channel,
    CohortStats,
    Idea,
    Media,
    RunStats,
    VideoSnapshot,
    media_id_of,
    run_id_of,
)

HISTORY_DAYS = 90
CHANNEL_CACHE_HOURS = 24
DB_WARN_BYTES = 350 * 1024 * 1024  # docs/03: shrink embeddings TTL to 60 days
DB_STOP_BYTES = 450 * 1024 * 1024  # docs/03: stop writing candidates
EMBEDDING_TTL_DEFAULT = 90
EMBEDDING_TTL_SHRUNK = 60
DESCRIPTION_MAX_CHARS = 500


@dataclass
class RunResult:
    run_id: str
    status: str  # ok | error
    stats: RunStats
    ideas: list[Idea] = field(default_factory=list)
    error: dict | None = None


class RunDigest:
    def __init__(
        self,
        store: DigestStore,
        source: VideoSource,
        embedder: Embedder,
        writer: IdeaWriter | None,
        image_host: ImageHost | None = None,
        chart: ChartRenderer | None = None,
        observer: Observer | None = None,
        clock: Callable[[], datetime] | None = None,
        max_ideas: int = 5,
        git_sha: str = "local",
        trigger: str = "workflow_dispatch",
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._source = source
        self._embedder = embedder
        self._writer = writer
        self._image_host = image_host
        self._chart = chart
        self._obs = observer or NullObserver()
        self._clock = clock or now_vn
        self._max_ideas = max_ideas
        self._git_sha = git_sha
        self._trigger = trigger
        self._sleep = sleep

    # ------------------------------------------------------------------ public

    def run(self) -> RunResult:
        started = self._clock()
        t0 = time.monotonic()
        run_id = run_id_of(started)

        config = self._store.get_app_config()
        if config.schema_version != SUPPORTED_SCHEMA_VERSION:
            # Stop before writing anything: the bot and the DDL disagree.
            raise FlashTrendError(
                E.SCHEMA_MISMATCH,
                f"app_config.schema_version={config.schema_version}, "
                f"bot expects {SUPPORTED_SCHEMA_VERSION}",
                {"expected": SUPPORTED_SCHEMA_VERSION, "found": config.schema_version},
                run_id,
            )

        region = config.regions[0] if config.regions else "VN"
        self._store.open_run(run_id, self._trigger, self._git_sha, region, started)
        self._obs.info(f"{run_id}: opened (regions={list(config.regions)})")

        stats = RunStats()
        ideas: list[Idea] = []
        chart_media_id: str | None = None
        error: FlashTrendError | None = None
        try:
            ideas, chart_media_id = self._pipeline(run_id, config, started, stats)
            error = self._add_llm(run_id, config, ideas)
        except FlashTrendError as exc:
            exc.trace_id = exc.trace_id or run_id
            error = exc
        except Exception as exc:  # noqa: BLE001 - every failure must close the run row
            error = FlashTrendError(E.UNEXPECTED, f"{type(exc).__name__}: {exc}", {}, run_id)

        stats.ideas_count = len(ideas)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        status = "error" if error else "ok"
        if error:
            self._obs.warn(f"{run_id}: {error.code} — {error.message}")
        else:
            self._cleanup(config)
        try:
            self._store.finish_run(
                run_id,
                status,
                self._clock(),
                stats,
                error.to_json() if error else None,
                chart_media_id,
            )
        except Exception as exc:  # noqa: BLE001
            self._obs.warn(f"{run_id}: could not close the run row ({exc})")
            if error is None:
                error = FlashTrendError(E.DB_WRITE, f"finish_run failed: {exc}", {}, run_id)
                status = "error"
        self._obs.info(
            f"{run_id}: {status} — collected {stats.collected}, scored {stats.scored}, "
            f"outliers {stats.outliers}, ideas {stats.ideas_count}, {stats.duration_ms} ms"
        )
        return RunResult(run_id, status, stats, ideas, error.to_json() if error else None)

    # --------------------------------------------------------------- pipeline

    def _pipeline(
        self, run_id: str, config: AppConfig, now: datetime, stats: RunStats
    ) -> tuple[list[Idea], str | None]:
        db_bytes = self._store.db_size_bytes()
        stop_candidates = False
        if db_bytes is not None:
            self._obs.info(f"{run_id}: database {db_bytes / 1024 / 1024:.1f} MB")
            if db_bytes >= DB_STOP_BYTES:
                stop_candidates = True
                self._obs.warn(f"{run_id}: database ≥ 450 MB — candidates are not written")
            elif db_bytes >= DB_WARN_BYTES:
                self._obs.warn(f"{run_id}: database ≥ 350 MB — embeddings TTL drops to 60 days")
        self._db_bytes = db_bytes

        # w2 — collect, channel baselines, videos, snapshots
        videos = self._source.collect(
            config.regions, config.keywords, now, config.chart_enabled, config.search_window_hours
        )
        stats.collected = len(videos)
        channels = self._baselines(videos, now)
        scorable = [v for v in videos if channels.get(v.channel_id, None) and
                    channels[v.channel_id].channel_avg_views > 0]
        if len(scorable) < len(videos):
            self._obs.warn(
                f"{run_id}: {len(videos) - len(scorable)} video(s) skipped (no channel baseline)"
            )
        self._store.upsert_videos(scorable, run_id, now)
        self._store.insert_snapshots(scorable, run_id, config.snapshot_ttl_days)

        # w3 — L1
        candidates, cohort = self._score(scorable, channels, config, now)
        stats.scored = len(candidates)
        stats.cohort = cohort
        outliers = [c for c in candidates if c.passed_z]
        stats.outliers = len(outliers)
        if not stop_candidates:
            self._store.insert_candidates(run_id, candidates, config.snapshot_ttl_days)
        self._obs.info(
            f"{run_id}: L1 cohort n={cohort.n} μ={_f(cohort.mu_ratio)} σ={_f(cohort.sigma_ratio)} "
            f"θ={cohort.z_threshold_used} → {len(outliers)}/{len(candidates)} outliers"
        )

        # w4 + w5 — L2 embeddings, clusters, history, ideas
        ideas = self._dedup(run_id, config, outliers, channels)
        if ideas:
            self._store.insert_ideas(run_id, ideas)

        chart_media_id = self._chart_image(run_id, ideas)
        return ideas, chart_media_id

    def _baselines(self, videos: list[VideoSnapshot], now: datetime) -> dict[str, Channel]:
        ids = sorted({v.channel_id for v in videos})
        cached = self._store.get_channels(ids) if ids else {}
        stale = [i for i in ids if i not in cached or cached[i].is_stale(now)]
        if stale:
            fresh = self._source.fetch_channels(stale, now)
            self._store.upsert_channels(fresh)
            cached.update({c.id: c for c in fresh})
        return cached

    def _score(
        self,
        videos: list[VideoSnapshot],
        channels: dict[str, Channel],
        config: AppConfig,
        now: datetime,
    ) -> tuple[list[Candidate], CohortStats]:
        ratios = [
            scoring.performance_ratio(v.views, channels[v.channel_id].channel_avg_views)
            for v in videos
        ]
        mu, sigma = scoring.cohort_mu_sigma(ratios)
        prior_m = scoring.median_raw_engagement(
            [(v.views, v.likes, v.comments) for v in videos],
            config.engagement_like_w,
            config.engagement_comment_w,
        )
        theta = scoring.choose_z_threshold(
            len(videos), config.z_threshold, config.relaxed_z_threshold, config.min_cohort_n
        )
        prev = self._store.previous_snapshots([v.id for v in videos], now, 2) if videos else {}

        candidates: list[Candidate] = []
        for v, ratio in zip(videos, ratios, strict=True):
            eng = scoring.engagement(
                v.views, v.likes, v.comments, prior_m or 0.0, config.bayes_c,
                config.engagement_like_w, config.engagement_comment_w,
            )
            decay = scoring.time_decay(v.age_hours, config.decay_lambda)
            z = scoring.z_score(ratio, mu, sigma)
            vel, acc = _velocity_acceleration(v, prev.get(v.id, []))
            candidates.append(
                Candidate(
                    video=v,
                    channel_avg_views=channels[v.channel_id].channel_avg_views,
                    performance_ratio=ratio,
                    z_score=z,
                    engagement=eng,
                    time_decay=decay,
                    viral_score=scoring.viral_score(v.views, eng, ratio, decay),
                    velocity=vel,
                    acceleration=acc,
                    passed_z=z >= theta,
                )
            )
        velocities = [c.velocity for c in candidates if c.velocity is not None]
        high = statistics.median(velocities) if velocities else None
        for c in candidates:
            c.early_flag = scoring.early_flag(c.velocity, c.acceleration, high)
        cohort = CohortStats(len(videos), mu, sigma, prior_m, theta)
        return candidates, cohort

    def _dedup(
        self,
        run_id: str,
        config: AppConfig,
        outliers: list[Candidate],
        channels: dict[str, Channel],
    ) -> list[Idea]:
        if not outliers:
            return []
        now = self._clock()
        ids = [c.video.id for c in outliers]
        hashes = {c.video.id: _text_hash(c.video.title) for c in outliers}
        known = self._store.get_embeddings(ids)
        vectors: dict[str, list[float]] = {}
        todo: list[str] = []
        for vid in ids:
            if vid in known and known[vid][0] == hashes[vid]:
                vectors[vid] = known[vid][1]  # same title as last time: reuse the vector
            else:
                todo.append(vid)
        if todo:
            titles = {c.video.id: c.video.title for c in outliers}
            encoded = self._embedder.encode([titles[v] for v in todo])
            rows = []
            for vid, vec in zip(todo, encoded, strict=True):
                vectors[vid] = [float(x) for x in vec]
                rows.append((vid, hashes[vid], "title", vectors[vid]))
            self._store.upsert_embeddings(rows, now)

        clusters = greedy_clusters(
            [vectors[i] for i in ids],
            [c.viral_score for c in outliers],
            config.cosine_threshold,
            run_id,
        )
        proposed = self._store.proposed_video_ids(HISTORY_DAYS)
        ideas: list[Idea] = []
        for cl in clusters:
            cand = outliers[cl.leader]
            vid = cand.video.id
            if vid in proposed:
                self._obs.info(f"{run_id}: {vid} already proposed in the last {HISTORY_DAYS} days")
                continue
            max_cos = self._store.nearest_history(vectors[vid], HISTORY_DAYS, ids)
            if max_cos is not None and max_cos >= config.history_cosine_threshold:
                self._obs.info(f"{run_id}: {vid} too close to history (cos {max_cos:.2f})")
                continue
            ideas.append(
                Idea(
                    candidate=cand,
                    channel_title=channels[cand.video.channel_id].title,
                    cluster_id=cl.cluster_id,
                    duplicates_count=cl.duplicates_count,
                    novelty_score=novelty_score(max_cos),
                    embedding=vectors[vid],
                )
            )
            if len(ideas) >= self._max_ideas:
                break
        self._obs.info(
            f"{run_id}: L2 {len(outliers)} outliers → {len(clusters)} clusters → {len(ideas)} ideas"
        )
        return ideas

    # ----------------------------------------------------------------- images

    def _chart_image(self, run_id: str, ideas: list[Idea]) -> str | None:
        """Chart PNG → image host → ``media``. A failure only loses the picture (docs/07)."""
        if not (self._chart and self._image_host and ideas):
            return None
        try:
            image = self._chart.render(run_id, ideas)
            if image is None:
                return None
            if len(image.png) > MAX_IMAGE_BYTES:
                self._obs.warn(f"{run_id}: chart > 2 MB, not uploaded")
                return None
            digest = hashlib.sha256(image.png).hexdigest()
            existing = self._store.find_media(digest)
            if existing:
                return existing.id
            url = self._image_host.upload(image.png, f"{run_id}.png")
            media = Media(
                id=media_id_of(digest), owner="flashtrend", kind="chart", url=url, host="nobinobi",
                sha256=digest, bytes=len(image.png), width=image.width, height=image.height,
                run_id=run_id,
            )
            self._store.insert_media(media)
            return media.id
        except Exception as exc:  # noqa: BLE001
            self._obs.warn(f"{run_id}: chart image skipped ({type(exc).__name__}: {exc})")
            return None

    # -------------------------------------------------------------------- LLM

    def _add_llm(self, run_id: str, config: AppConfig, ideas: list[Idea]) -> FlashTrendError | None:
        if not ideas:
            return None
        if not config.llm_enabled or self._writer is None:
            return FlashTrendError(
                E.LLM_DISABLED, "llm_enabled is false: ideas kept with llm = null", {}, run_id
            )
        for idea in ideas:
            brief = IdeaBrief(
                title=idea.candidate.video.title,
                description=idea.candidate.video.description[:DESCRIPTION_MAX_CHARS],
                channel_title=idea.channel_title,
                url=idea.candidate.video.url,
                views=idea.candidate.video.views,
                likes=idea.candidate.video.likes,
                comments=idea.candidate.video.comments,
                age_hours=idea.candidate.video.age_hours,
                performance_ratio=idea.candidate.performance_ratio,
                duplicates_count=idea.duplicates_count,
            )
            llm = self._write_valid(brief, run_id, idea.video_id)  # raises FlashTrendError
            idea.llm = llm
            self._store.update_idea_llm(run_id, idea.video_id, llm)
        return None

    def _write_valid(self, brief: IdeaBrief, run_id: str, video_id: str) -> dict:
        last = ""
        for attempt in (1, 2):  # wrong schema → retry once (docs/02)
            raw = self._writer.write(brief)  # type: ignore[union-attr]
            try:
                return validate_llm(raw)
            except LlmSchemaError as exc:
                last = str(exc)
                self._obs.warn(f"{run_id}: {video_id} llm schema attempt {attempt}: {last}")
        raise FlashTrendError(
            E.GEMINI_SCHEMA, f"{video_id}: {last}", {"video_id": video_id}, run_id
        )

    # ---------------------------------------------------------------- cleanup

    def _cleanup(self, config: AppConfig) -> None:
        shrunk = self._db_bytes is not None and self._db_bytes >= DB_WARN_BYTES
        try:
            counts = self._store.cleanup(
                config.snapshot_ttl_days,
                EMBEDDING_TTL_SHRUNK if shrunk else EMBEDDING_TTL_DEFAULT,
            )
            self._obs.info(f"TTL cleanup: {counts}")
        except Exception as exc:  # noqa: BLE001 - housekeeping never fails the run
            self._obs.warn(f"TTL cleanup skipped ({type(exc).__name__}: {exc})")

    _db_bytes: int | None = None


def _velocity_acceleration(video: VideoSnapshot, prev) -> tuple[float | None, float | None]:
    if not prev:
        return None, None
    p1 = prev[0]
    vel = scoring.velocity(p1.views, p1.captured_at.timestamp(), video.views,
                           video.captured_at.timestamp())
    if vel is None or len(prev) < 2:
        return vel, None
    p2 = prev[1]
    prev_vel = scoring.velocity(p2.views, p2.captured_at.timestamp(), p1.views,
                                p1.captured_at.timestamp())
    if prev_vel is None:
        return vel, None
    acc = scoring.acceleration(prev_vel, p1.captured_at.timestamp(), vel,
                               video.captured_at.timestamp())
    return vel, acc


def _text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _f(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
