"""Analysis charts of one run: what a data analyst would look at before choosing an idea.

All of them read the run's scored candidates (and the last runs for the timeline) — nothing is fetched here.
A chart that the data cannot support (no long videos, one run only…) is left out rather than drawn empty.
Positions: 1 is the top-ideas card (drawn by :mod:`infrastructure.chart`), 2–8 are below.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from matplotlib.ticker import FuncFormatter

from application.ports import AnalysisImage, RunPoint
from domain.clock import to_vn
from domain.models import Candidate, Idea
from infrastructure.chart import (
    ACCENT,
    BG,
    GOLD,
    GRID,
    HEIGHT_PX,
    MUTED,
    PANEL,
    PLATFORM_COLOR,
    PLATFORM_NAME,
    TEAL,
    TEXT,
    VIOLET,
    WIDTH_PX,
    clean_label,
    compact,
    frame,
    gradient_colors,
    shorten,
    to_png,
)

MIN_POINTS = 5  # fewer candidates than this make a distribution chart meaningless

DURATION_BUCKETS = (  # (label, upper bound in seconds)
    ("< 1 giờ", 3600), ("1–4 giờ", 14400), ("4–8 giờ", 28800), ("8–24 giờ", 86400), ("> 24 giờ", None),
)


def _color(platform: str) -> str:
    return PLATFORM_COLOR.get(platform, ACCENT)


def _name(platform: str) -> str:
    return PLATFORM_NAME.get(platform, platform)


def _by_platform(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        out[c.video.platform].append(c)
    return dict(sorted(out.items()))


def _legend(ax, **kw) -> None:
    leg = ax.legend(frameon=False, labelcolor=TEXT, fontsize=10, **kw)
    for handle in getattr(leg, "legend_handles", []):
        handle.set_alpha(1)


def _style(ax, grid: str = "y") -> None:
    ax.set_facecolor(PANEL)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


class AnalysisCharts:
    def render(
        self,
        run_id: str,
        now: datetime,
        candidates: list[Candidate],
        ideas: list[Idea],
        history: list[RunPoint],
    ) -> list[AnalysisImage]:
        made = (
            (2, "scatter", "Lượt xem và z-score", self._scatter),
            (3, "zscore", "Phân bố z-score theo nền tảng", self._zscore),
            (4, "platform", "Tỉ trọng nền tảng", self._platform),
            (5, "duration", "Thời lượng video", self._duration),
            (6, "hours", "Giờ đăng (giờ Việt Nam)", self._hours),
            (7, "keywords", "Từ khoá hiệu quả nhất", self._keywords),
            (8, "timeline", "Các lần chạy gần đây", self._timeline),
        )
        out: list[AnalysisImage] = []
        for position, slug, caption, draw in made:
            fig = draw(run_id, now, candidates, ideas, history)
            if fig is not None:
                out.append(AnalysisImage(slug, caption, position, to_png(fig), WIDTH_PX, HEIGHT_PX))
        return out

    # ------------------------------------------------------------------ charts

    def _scatter(self, run_id, now, candidates, ideas, history):
        usable = [c for c in candidates if c.video.views > 0]
        if len(usable) < MIN_POINTS:
            return None
        n_out = sum(1 for c in usable if c.passed_z)
        fig, ax = frame("Lượt xem và z-score", f"{len(usable)} video · {n_out} vượt ngưỡng (vòng vàng)",
                        run_id, now)
        _style(ax, "both")
        for platform, items in _by_platform(usable).items():
            ax.scatter([c.video.views for c in items], [c.z_score for c in items], s=38, alpha=0.78,
                       color=_color(platform), label=f"{_name(platform)} ({len(items)})", linewidths=0)
        out = [c for c in usable if c.passed_z]
        ax.scatter([c.video.views for c in out], [c.z_score for c in out], s=130, facecolors="none",
                   edgecolors=GOLD, linewidths=1.8, zorder=3)
        middle = statistics.geometric_mean([c.video.views for c in usable])
        for c in sorted(out, key=lambda c: -c.viral_score)[:3]:
            right_half = c.video.views > middle  # labels of the right half grow leftwards, inside the panel
            ax.annotate(shorten(clean_label(c.video.title), 26), (c.video.views, c.z_score),
                        xytext=(-10 if right_half else 10, -16), textcoords="offset points",
                        ha="right" if right_half else "left", color=TEXT, fontsize=9)
        ax.set_xscale("log")
        ax.set_xlabel("Lượt xem (thang log)")
        ax.set_ylabel("z-score trong nền tảng")
        ax.axhline(0, color=GRID, linewidth=1.2)
        _legend(ax, loc="upper left")
        return fig

    def _zscore(self, run_id, now, candidates, ideas, history):
        if len(candidates) < MIN_POINTS:
            return None
        import numpy as np

        groups = _by_platform(candidates)
        values = [c.z_score for c in candidates]
        bins = np.linspace(min(values), max(values), 24) if max(values) > min(values) else 10
        fig, ax = frame("Phân bố z-score theo nền tảng", "Vạch đứt: ngưỡng θ của từng nền tảng (z thấp nhất "
                        "trong nhóm vượt ngưỡng)", run_id, now)
        _style(ax)
        for platform, items in groups.items():
            ax.hist([c.z_score for c in items], bins=bins, alpha=0.62, color=_color(platform),
                    label=f"{_name(platform)} (n={len(items)})", edgecolor=BG, linewidth=0.6)
            passed = [c.z_score for c in items if c.passed_z]
            if passed:
                ax.axvline(min(passed), color=_color(platform), linestyle="--", linewidth=1.6)
        ax.set_xlabel("z-score")
        ax.set_ylabel("Số video")
        _legend(ax, loc="upper right")
        return fig

    def _platform(self, run_id, now, candidates, ideas, history):
        groups = _by_platform(candidates)
        if not groups:
            return None
        counts = [len(v) for v in groups.values()]
        views = [sum(c.video.views for c in v) for v in groups.values()]
        sub = f"{sum(counts)} video · {compact(sum(views))} lượt xem"
        fig, base = frame("Tỉ trọng nền tảng", sub, run_id, now)
        base.set_axis_off()  # the donuts have their own axes; the frame's would show a 0–1 grid behind them
        for pos, (title, data, total) in enumerate((("Số video", counts, str(sum(counts))),
                                                     ("Lượt xem", views, compact(sum(views))))):
            ax = fig.add_axes([0.08 + pos * 0.45, 0.12, 0.38, 0.62])
            ax.set_axis_off()
            ax.pie(data, colors=[_color(p) for p in groups], startangle=90, counterclock=False,
                   wedgeprops={"width": 0.26, "edgecolor": BG, "linewidth": 3})
            ax.text(0, 0.06, total, ha="center", va="center", fontsize=24, fontweight="bold", color=TEXT)
            ax.text(0, -0.2, title, ha="center", va="center", fontsize=11, color=MUTED)
            share = "  ·  ".join(f"{_name(p)} {v / sum(data):.0%}" for p, v in zip(groups, data, strict=True))
            ax.set_title(share, color=TEXT, fontsize=12, pad=4)
        from matplotlib.patches import Patch

        fig.legend(handles=[Patch(color=_color(p), label=_name(p)) for p in groups], loc="lower center",
                   ncol=len(groups), frameon=False, labelcolor=TEXT, fontsize=11, bbox_to_anchor=(0.5, 0.045))
        return fig

    def _duration(self, run_id, now, candidates, ideas, history):
        timed = [c for c in candidates if c.video.duration_sec]
        if len(timed) < MIN_POINTS:
            return None
        labels = [b[0] for b in DURATION_BUCKETS]

        def bucket(seconds: int) -> int:
            return next(i for i, (_, hi) in enumerate(DURATION_BUCKETS) if hi is None or seconds < hi)

        groups = _by_platform(timed)
        long_n = sum(1 for c in timed if c.video.duration_sec >= 14400)
        fig, ax = frame("Thời lượng video", f"{long_n}/{len(timed)} video dài từ 4 giờ — tuyển tập nhiều "
                        "tập", run_id, now)
        _style(ax)
        bottoms = [0] * len(labels)
        for platform, items in groups.items():
            counts = [0] * len(labels)
            for c in items:
                counts[bucket(c.video.duration_sec)] += 1
            ax.bar(labels, counts, bottom=bottoms, color=_color(platform), label=_name(platform), width=0.62)
            bottoms = [b + n for b, n in zip(bottoms, counts, strict=True)]
        for x, total in enumerate(bottoms):
            if total:
                ax.text(x, total + max(bottoms) * 0.02, str(total), ha="center", color=TEXT, fontsize=11,
                        fontweight="bold")
        ax.set_ylabel("Số video")
        _legend(ax, loc="upper right")
        return fig

    def _hours(self, run_id, now, candidates, ideas, history):
        if len(candidates) < MIN_POINTS:
            return None
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap

        groups = _by_platform(candidates)
        grid = np.zeros((len(groups), 24), dtype=int)
        for row, items in enumerate(groups.values()):
            for c in items:
                grid[row, to_vn(c.video.published_at).hour] += 1
        fig, ax = frame("Giờ đăng (giờ Việt Nam)", "Video thu được theo giờ đăng; ô đậm = nhiều video",
                        run_id, now)
        heat = LinearSegmentedColormap.from_list("t", [PANEL, "#2c3a9e", VIOLET, TEAL])
        ax.imshow(grid, aspect="auto", cmap=heat)
        ax.set_xticks(range(24), [f"{h:02d}" for h in range(24)], fontsize=9)
        ax.set_yticks(range(len(groups)), [_name(p) for p in groups], fontsize=11)
        peak = grid.max() or 1
        for (r, h), n in np.ndenumerate(grid):
            if n:
                ax.text(h, r, str(n), ha="center", va="center", fontsize=9,
                        color=BG if n > peak * 0.55 else TEXT)
        ax.set_xlabel("Giờ trong ngày")
        for side in ax.spines.values():
            side.set_visible(False)
        return fig

    def _keywords(self, run_id, now, candidates, ideas, history):
        tags: dict[str, list[Candidate]] = defaultdict(list)
        for c in candidates:
            if c.video.query_tag:
                tags[c.video.query_tag].append(c)
        rows = sorted(((statistics.median(c.video.views for c in v), tag, v) for tag, v in tags.items()
                       if len(v) >= 2), reverse=True)[:10]
        if len(rows) < 2:
            return None
        fig, ax = frame("Từ khoá hiệu quả nhất", "Lượt xem trung vị của video tìm được theo từ khoá "
                        "(n = số video)", run_id, now)
        _style(ax, "x")
        ax.set_position([0.24, 0.11, 0.72, 0.64])
        rows.reverse()
        names = [self._tag_name(tag) for _, tag, _ in rows]
        values = [m for m, _, _ in rows]
        colors = gradient_colors(len(rows))[::-1]  # the top bar is teal, the bottom one violet
        bars = ax.barh(names, values, color=colors, height=0.62)
        for bar, (m, _, v) in zip(bars, rows, strict=True):
            ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{compact(m)}  ·  n={len(v)}", va="center", color=TEXT, fontsize=10)
        ax.set_xlim(0, max(values) * 1.22)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: compact(x)))
        ax.set_xlabel("Lượt xem trung vị")
        return fig

    @staticmethod
    def _tag_name(tag: str) -> str:
        return shorten(clean_label(tag) or tag, 30)

    def _timeline(self, run_id, now, candidates, ideas, history):
        outliers = sum(1 for c in candidates if c.passed_z)
        points = [*history, RunPoint(now, len(candidates), outliers, len(ideas))]
        if len(points) < 3:
            return None
        xs = [to_vn(p.started_at) for p in points]
        sub = f"{len(points)} lần chạy mới nhất · video thu được và outlier"
        fig, ax = frame("Các lần chạy gần đây", sub, run_id, now)
        _style(ax)
        ax.plot(xs, [p.collected for p in points], color=TEAL, linewidth=2.4, marker="o", markersize=4,
                label="Video thu được")
        ax.set_ylabel("Video thu được", color=TEAL)
        twin = ax.twinx()
        twin.bar(xs, [p.outliers for p in points], width=0.02, color=VIOLET, alpha=0.7, label="Outlier")
        twin.set_facecolor(PANEL)
        twin.patch.set_visible(True)
        ax.set_zorder(twin.get_zorder() + 1)  # the line is drawn over the bars
        ax.patch.set_visible(False)
        twin.set_ylabel("Outlier", color=VIOLET)
        twin.tick_params(colors=MUTED, length=0)
        for side in ("top", "right"):
            twin.spines[side].set_visible(False)
        import matplotlib.dates as mdates

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh", tz=xs[0].tzinfo))
        ax.margins(x=0.03)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = twin.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, frameon=False, labelcolor=TEXT, loc="upper left", fontsize=10)
        return fig

