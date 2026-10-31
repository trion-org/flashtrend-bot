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
from dataclasses import dataclass, field, replace
from datetime import datetime

from application.observer import NullObserver, Observer
from application.ports import (
    AnalysisRenderer,
    ChartRenderer,
    DigestStore,
    Embedder,
    IdeaBrief,
    IdeaWriter,
    ImageHost,
    RunPoint,
    TitleTranslator,
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
    HotVideo,
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
HOT_LIST_SIZE = 10  # hot_videos rows per run
HOT_SPARE = 5  # extra candidates checked, to fill the list when a checked video turns out too short
CARD_SIZE = 8  # videos on the top card
HISTORY_RUNS = 48  # past runs on the timeline chart
GROWTH_POINTS = 72  # earlier snapshots per hot video on the growth chart (three days of hourly runs)


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
        analysis: AnalysisRenderer | None = None,
        observer: Observer | None = None,
        clock: Callable[[], datetime] | None = None,
        max_ideas: int = 5,
        git_sha: str = "local",
        trigger: str = "workflow_dispatch",
        sleep: Callable[[float], None] = time.sleep,
        translator: TitleTranslator | None = None,
    ) -> None:
        self._store = store
        self._translator = translator
        self._source = source
        self._embedder = embedder
        self._writer = writer
        self._image_host = image_host
        self._chart = chart
        self._analysis = analysis
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
        full = self._trigger != "schedule"  # a manual run always does everything
        ask_youtube = full or now.hour % max(1, config.youtube_search_every_hours) == 0
        if not ask_youtube:
            self._obs.info(
                f"{run_id}: YouTube search skipped (every {config.youtube_search_every_hours} h: quota)"
            )
        videos = self._source.collect(
            config.regions,
            config.keywords if ask_youtube else (),
            now,
            config.chart_enabled and ask_youtube,
            config.search_window_hours,
            config.bilibili_keywords,
            config.min_duration_sec,
        )
        stats.collected = len(videos)
        videos = self._relevant(run_id, videos, config)
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

        niche = {
            c.video.id: scoring.niche_match(c.video.title, c.video.description, config.niche_terms,
                                            config.niche_exclude_terms)
            for c in candidates
        }
        if config.niche_boost > 1 and any(niche.get(c.video.id) for c in outliers):
            self._obs.info(
                f"{run_id}: niche ×{config.niche_boost:g} for "
                f"{sum(1 for c in outliers if niche.get(c.video.id))}/{len(outliers)} outlier(s)"
            )

        # w4 + w5 — L2 embeddings, clusters, history, ideas
        ideas = self._dedup(run_id, config, outliers, channels, niche)
        if ideas:
            self._store.insert_ideas(run_id, ideas)

        picks = self._hot(run_id, config, now, candidates, channels, niche)
        # this run on the timeline, counted like the stored ones (videos collected, not only those scored)
        current = RunPoint(now, stats.collected, stats.outliers, len(ideas))
        chart_media_id = self._images(run_id, config, now, candidates, ideas, picks, current)
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
        # One cohort per platform: a YouTube ratio is views / the channel's average views, a Bilibili one
        # is views / followers — their means and spreads must never be mixed into one Z-Score.
        cohorts: dict[str, tuple[float | None, float | None, float]] = {}
        for platform in sorted({v.platform for v in videos}):
            members = [r for v, r in zip(videos, ratios, strict=True) if v.platform == platform]
            p_mu, p_sigma = scoring.cohort_mu_sigma(members)
            p_theta = scoring.choose_z_threshold(
                len(members), config.z_threshold, config.relaxed_z_threshold, config.min_cohort_n
            )
            cohorts[platform] = (p_mu, p_sigma, p_theta)
        prior_m = scoring.median_raw_engagement(
            [(v.views, v.likes, v.comments) for v in videos],
            config.engagement_like_w,
            config.engagement_comment_w,
        )
        prev = self._store.previous_snapshots([v.id for v in videos], now, 2) if videos else {}

        candidates: list[Candidate] = []
        for v, ratio in zip(videos, ratios, strict=True):
            eng = scoring.engagement(
                v.views, v.likes, v.comments, prior_m or 0.0, config.bayes_c,
                config.engagement_like_w, config.engagement_comment_w,
            )
            decay = scoring.time_decay(v.age_hours, config.decay_lambda)
            mu, sigma, theta = cohorts[v.platform]
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
                    z_threshold=theta,
                )
            )
        velocities = [c.velocity for c in candidates if c.velocity is not None]
        high = statistics.median(velocities) if velocities else None
        for c in candidates:
            c.early_flag = scoring.early_flag(c.velocity, c.acceleration, high)
        # the run row records the largest platform's cohort; the others are logged
        sizes = {p: sum(1 for v in videos if v.platform == p) for p in cohorts}
        main = max(sizes, key=lambda p: (sizes[p], p == "youtube")) if sizes else None
        mu, sigma, theta = cohorts[main] if main else (None, None, config.z_threshold)
        if len(cohorts) > 1:
            self._obs.info("cohorts: " + "; ".join(
                f"{p} n={sizes[p]} μ={_f(cohorts[p][0])} σ={_f(cohorts[p][1])} θ={cohorts[p][2]}"
                for p in cohorts))
        cohort = CohortStats(sizes[main] if main else 0, mu, sigma, prior_m, theta)
        return candidates, cohort

    def _dedup(
        self,
        run_id: str,
        config: AppConfig,
        outliers: list[Candidate],
        channels: dict[str, Channel],
        niche: dict[str, bool],
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
            [_priority(c, config, niche) for c in outliers],
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
                    niche=niche.get(vid, False),
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

    # ------------------------------------------------------------- hot videos

    def _hot(
        self,
        run_id: str,
        config: AppConfig,
        now: datetime,
        candidates: list[Candidate],
        channels: dict[str, Channel],
        niche: dict[str, bool],
    ) -> list[Idea]:
        """Hottest by priority (niche first): Bilibili's go to ``hot_videos``, the top of all to the card."""
        ranked = sorted(candidates, key=lambda c: _priority(c, config, niche), reverse=True)

        def title_of(c: Candidate) -> str:
            ch = channels.get(c.video.channel_id)
            return ch.title if ch else c.video.channel_id

        bilibili = [c for c in ranked if c.video.platform == "bilibili"][: HOT_LIST_SIZE + HOT_SPARE]
        parts = self._verified_parts(run_id, [c.video.id for c in bilibili])
        shown: list[Candidate] = []
        for c in bilibili:
            total = sum(parts.get(c.video.id, ()))
            if parts.get(c.video.id) and total < config.min_duration_sec:
                self._obs.info(f"{run_id}: {c.video.id} left out of the hot list: its parts add up to "
                               f"{total / 3600:.1f} h")
                continue
            shown.append(c)
        rows = [
            self._hot_row(i, c, title_of(c), niche.get(c.video.id, False), parts.get(c.video.id))
            for i, c in enumerate(shown[:HOT_LIST_SIZE], start=1)
        ]
        rows += self._series_rows(run_id, config, now)
        # every title a Vietnamese reader meets — the hot list, the card, the charts' hot videos — translated
        cards, hot = ranked[:CARD_SIZE], [c for c in candidates if c.passed_z]
        vi = self._titles_vi(run_id, [r.title for r in rows] + [c.video.title for c in (*cards, *hot)])
        rows = [replace(r, title_vi=vi.get(r.title)) for r in rows]
        for c in candidates:
            c.title_vi = vi.get(c.video.title)
        if rows:
            try:
                self._store.insert_hot_videos(run_id, rows)
            except Exception as exc:  # noqa: BLE001 - sql/07 not applied yet, or a blip: the digest goes on
                self._obs.warn(f"{run_id}: hot_videos not written ({type(exc).__name__}: {exc})")
        return [
            Idea(candidate=c, channel_title=title_of(c), cluster_id="hot", niche=niche.get(c.video.id, False))
            for c in ranked[:CARD_SIZE]
        ]

    @staticmethod
    def _hot_row(rank: int, c: Candidate, channel: str, in_niche: bool, parts: list[int] | None) -> HotVideo:
        """A hot-list row; a checked video carries the total of its parts as its length, how many parts there
        are, and how long part 1 is (what the player opens on)."""
        total = sum(parts) if parts else c.video.duration_sec
        return HotVideo(
            "video", rank, c.video.id, c.video.platform, c.video.title, c.video.url, channel,
            c.video.views, total, c.video.published_at, in_niche, c.viral_score,
            parts=len(parts) if parts else None, first_part_sec=parts[0] if parts else None,
        )

    def _titles_vi(self, run_id: str, titles: list[str]) -> dict[str, str]:
        """``{title: Vietnamese}``: the stored translations, the rest asked of the translator in one go and
        stored, so a title is translated once. Never fails the run — an untranslated title shows as it is."""
        wanted = list(dict.fromkeys(t for t in titles if t and t.strip()))
        if not wanted:
            return {}
        keys = {t: _text_hash(t) for t in wanted}
        try:
            known = self._store.get_titles_vi(list(keys.values()))
        except Exception as exc:  # noqa: BLE001 - sql/08 not applied yet, or a blip
            self._obs.warn(f"{run_id}: stored title translations unavailable ({type(exc).__name__}: {exc})")
            known = {}
        out = {t: known[k] for t, k in keys.items() if k in known}
        ask = [t for t in wanted if t not in out]
        if not ask or self._translator is None:
            return out
        try:
            got = self._translator.translate(ask)
        except Exception as exc:  # noqa: BLE001 - the original titles still read
            self._obs.warn(f"{run_id}: titles not translated ({type(exc).__name__}: {exc})")
            return out
        new = [(keys[t], t, vi.strip()) for t, vi in zip(ask, got, strict=False) if vi and vi.strip()]
        out.update({t: vi for _, t, vi in new})
        if new:
            try:
                self._store.upsert_titles_vi(new)
            except Exception as exc:  # noqa: BLE001 - asked again next run
                self._obs.warn(f"{run_id}: title translations not stored ({type(exc).__name__}: {exc})")
        self._obs.info(f"{run_id}: {len(new)} title(s) translated to Vietnamese, {len(out) - len(new)} known")
        return out

    def _verified_parts(self, run_id: str, video_ids: list[str]) -> dict[str, list[int]]:
        """Part lengths of the hot-list candidates; {} when the source cannot answer (rows stay unchecked)."""
        if not video_ids:
            return {}
        try:
            found = self._source.video_parts(video_ids)
        except Exception as exc:  # noqa: BLE001 - the list is still useful without the counts
            self._obs.warn(f"{run_id}: part lengths not checked ({type(exc).__name__}: {exc})")
            return {}
        if len(found) < len(video_ids):
            self._obs.warn(f"{run_id}: parts checked for {len(found)} of {len(video_ids)} hot video(s)")
        return found

    def _relevant(self, run_id: str, videos: list[VideoSnapshot], config: AppConfig) -> list[VideoSnapshot]:
        """Keep only what the feed is about: long enough (a compilation, not a clip) and, if asked, the niche.

        Runs before the channel baselines, so a channel is only looked up for a video that will be scored.
        """
        kept = videos
        if config.min_duration_sec:
            kept = [v for v in kept if (v.duration_sec or 0) >= config.min_duration_sec]
        too_short = len(videos) - len(kept)
        if config.niche_only:
            kept = [v for v in kept if scoring.niche_match(v.title, v.description, config.niche_terms,
                                                           config.niche_exclude_terms)]
        if len(kept) < len(videos):
            self._obs.info(
                f"{run_id}: kept {len(kept)} of {len(videos)} video(s): {too_short} shorter than "
                f"{config.min_duration_sec / 3600:g} h, {len(videos) - too_short - len(kept)} not the niche"
            )
        return kept

    def _series_rows(self, run_id: str, config: AppConfig, now: datetime) -> list[HotVideo]:
        """Bilibili's live 国创 series ranking as ``kind = series`` rows; never fails the run."""
        if not config.bilibili_series_types:
            return []
        try:
            series = self._source.hot_series(config.bilibili_series_types, now)
        except Exception as exc:  # noqa: BLE001 - one more list is not worth a run
            self._obs.warn(f"{run_id}: series ranking skipped ({type(exc).__name__}: {exc})")
            return []
        self._obs.info(f"{run_id}: {len(series)} hot series from the ranking")
        descriptor = lambda s: " · ".join(x for x in (s.rating, s.episodes) if x) or None  # noqa: E731
        return [
            HotVideo("series", s.rank, f"bi_ss{s.season_id}", "bilibili", s.title, s.url, descriptor(s),
                     s.views, None, None, True, 0.0)
            for s in series[:HOT_LIST_SIZE]
        ]

    # ----------------------------------------------------------------- images

    def _images(
        self,
        run_id: str,
        config: AppConfig,
        now: datetime,
        candidates: list[Candidate],
        ideas: list[Idea],
        picks: list[Idea],
        current: RunPoint | None = None,
    ) -> str | None:
        """The top card and the analysis charts → image host → ``media``. Never fails the run (docs/07)."""
        if not (self._image_host and (self._chart or self._analysis) and picks):
            return None
        if self._trigger == "schedule" and now.hour % max(1, config.analysis_every_hours):
            self._obs.info(
                f"{run_id}: charts skipped (every {config.analysis_every_hours} h: image host load)"
            )
            return None
        card_id: str | None = None
        if self._chart:
            try:
                image = self._chart.render(run_id, picks)
                if image:
                    card_id = self._publish(
                        run_id, image.png, image.width, image.height, "top", "Video đang hot", 1
                    )
            except Exception as exc:  # noqa: BLE001
                self._obs.warn(f"{run_id}: top chart skipped ({type(exc).__name__}: {exc})")
        if self._analysis:
            try:
                history = self._store.recent_runs(HISTORY_RUNS)
            except Exception as exc:  # noqa: BLE001 - only the timeline chart needs it
                self._obs.warn(f"{run_id}: run history unavailable ({type(exc).__name__}: {exc})")
                history = []
            hot = [c.video.id for c in candidates if c.passed_z]
            try:
                growth = self._store.previous_snapshots(hot, now, GROWTH_POINTS) if hot else {}
            except Exception as exc:  # noqa: BLE001 - only the growth chart needs them
                self._obs.warn(f"{run_id}: snapshots for the growth chart unavailable "
                               f"({type(exc).__name__}: {exc})")
                growth = {}
            try:
                points = [*history, current] if current else history
                images = self._analysis.render(run_id, now, candidates, ideas, points, growth)
            except Exception as exc:  # noqa: BLE001
                self._obs.warn(f"{run_id}: analysis charts skipped ({type(exc).__name__}: {exc})")
                images = []
            done = 0
            for img in images:
                if self._publish(
                    run_id, img.png, img.width, img.height, img.slug, img.caption, img.position
                ):
                    done += 1
            self._obs.info(f"{run_id}: {done}/{len(images)} analysis chart(s) published")
        return card_id

    def _publish(
        self, run_id: str, png: bytes, width: int, height: int, slug: str, caption: str, position: int
    ) -> str | None:
        """PNG → image host → ``media`` (kind ``analysis``); the id, or None when this image was skipped."""
        try:
            if len(png) > MAX_IMAGE_BYTES:
                self._obs.warn(f"{run_id}: {slug} chart > 2 MB, not uploaded")
                return None
            digest = hashlib.sha256(png).hexdigest()
            existing = self._store.find_media(digest)
            if existing:
                return existing.id
            url = self._image_host.upload(png, f"{run_id}_{slug}.png")
            media = Media(
                id=media_id_of(digest), owner="flashtrend", kind="analysis", url=url, host="nobinobi",
                sha256=digest, bytes=len(png), width=width, height=height, run_id=run_id,
                caption=caption, position=position,
            )
            self._store.insert_media(media)
            return media.id
        except Exception as exc:  # noqa: BLE001
            self._obs.warn(f"{run_id}: {slug} chart skipped ({type(exc).__name__}: {exc})")
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


def _priority(c: Candidate, config: AppConfig, niche: dict[str, bool]) -> float:
    """What orders ideas and the hot list: viral_score, times ``niche_boost`` for a niche video."""
    return c.viral_score * (config.niche_boost if niche.get(c.video.id) else 1.0)


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
