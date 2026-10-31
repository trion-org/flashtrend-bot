"""Analysis charts of one run: what a data analyst would look at before choosing an idea.

All of them read the run's scored candidates (the hot videos' earlier snapshots for the growth chart, the last
runs for the timeline) — nothing is fetched here. A chart that the data cannot support (no long videos, one
run only…) is left out rather than drawn empty. Positions: 1 is the top-ideas card (drawn by
:mod:`infrastructure.chart`), 2–8 are below.

Each chart says how to read it twice, for someone who never read a statistics book: a one-line subtitle on
the image, and a caption (shown under the photo in Telegram) with what one mark means and what this run's
data says.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from matplotlib.ticker import FuncFormatter

from application.ports import AnalysisImage, RunPoint
from domain.clock import to_vn
from domain.models import Candidate, Idea, PreviousSnapshot
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
    frame,
    gradient_colors,
    shorten,
    to_png,
)

MIN_POINTS = 5  # fewer candidates than this make a distribution chart meaningless
#: hot videos drawn on the growth chart: lines cross, and only three categorical colours stay apart for every
#: reader (the dataviz validator, all pairs, colour-blind included, on PANEL)
GROWTH_LINES = 3
LINE_COLORS = ("#3987e5", "#d95926", "#199e70")  # blue, orange, aqua

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


def _num(x: float) -> str:
    """A count the Vietnamese way: 1.2M → ``1,2 triệu``, 45.6K → ``45,6 nghìn``."""
    x = float(x)
    for unit, size in (("tỷ", 1e9), ("triệu", 1e6), ("nghìn", 1e3)):
        if abs(x) >= size:
            return f"{x / size:.1f}".replace(".0", "").replace(".", ",") + f" {unit}"
    return f"{x:.0f}"


def _decimal(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _time_axis(ax, times: list[datetime]) -> None:
    """Hours along the time axis; the day under them only when the times span more than one."""
    import matplotlib.dates as mdates

    tz = times[0].tzinfo
    days = sorted({t.date() for t in times})
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(tz=tz, minticks=4, maxticks=9))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M" if len(days) == 1 else "%H:%M\n%d/%m", tz=tz))
    ax.set_xlabel(f"Giờ Việt Nam, ngày {days[0]:%d/%m}" if len(days) == 1 else "Giờ Việt Nam")


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
        growth: dict[str, list[PreviousSnapshot]] | None = None,
    ) -> list[AnalysisImage]:
        """Every chart the data supports; ``history`` = the last runs, this one last (the timeline);
        ``growth`` = the hot videos' earlier snapshots, any order (the growth chart)."""
        made = (
            (2, "growth", "Tăng trưởng lượt xem của video hot", lambda: self._growth(run_id, now, candidates,
                                                                                      growth or {})),
            (3, "scatter", "Lượt xem và mức vượt kênh", lambda: self._scatter(run_id, now, candidates)),
            (4, "platform", "Tỉ trọng nền tảng", lambda: self._platform(run_id, now, candidates)),
            (5, "duration", "Thời lượng video", lambda: self._duration(run_id, now, candidates)),
            (6, "hours", "Giờ đăng (giờ Việt Nam)", lambda: self._hours(run_id, now, candidates)),
            (7, "keywords", "Từ khoá hiệu quả nhất", lambda: self._keywords(run_id, now, candidates)),
            (8, "timeline", "Các lần chạy gần đây", lambda: self._timeline(run_id, now, history)),
        )
        out: list[AnalysisImage] = []
        for position, slug, title, draw in made:
            drawn = draw()
            if drawn is not None:
                fig, note = drawn
                out.append(AnalysisImage(slug, f"{title}\n{note}", position, to_png(fig), WIDTH_PX,
                                         HEIGHT_PX))
        return out

    # ------------------------------------------------------------------ charts

    def _growth(self, run_id, now, candidates, growth):
        series = []
        for c in candidates:
            if not c.passed_z:
                continue
            seen = {p.captured_at: p.views for p in growth.get(c.video.id, [])}
            seen[c.video.captured_at] = c.video.views
            points = sorted(seen.items())
            hours = (points[-1][0] - points[0][0]).total_seconds() / 3600 if len(points) >= 2 else 0
            if hours > 0:
                series.append(((points[-1][1] - points[0][1]) / hours, c, points))
        if not series:
            return None
        series.sort(key=lambda s: -s[0])
        shown = series[:GROWTH_LINES]
        fig, ax = frame("Tăng trưởng lượt xem của video hot",
                        "Lượt xem tăng thêm kể từ lần đo đầu (đo mỗi giờ) · "
                        "đường càng dốc = video càng hút người xem",
                        run_id, now)
        _style(ax, "both")
        ends = []
        for color, (rate, c, points) in zip(LINE_COLORS, shown, strict=False):
            xs = [to_vn(t) for t, _ in points]
            ys = [v - points[0][1] for _, v in points]
            ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=6, markeredgecolor=PANEL,
                    markeredgewidth=1.5, label=(f"{_name(c.video.platform)} · "
                                                f"{shorten(clean_label(c.shown_title), 34)}"))
            ends.append((ys[-1], xs[-1], f"+{_num(rate)}/giờ"))
        top = max(max(y for y, _, _ in ends), 1)
        ax.set_ylim(0, top * 1.25)
        gap, placed = top * 0.08, []
        for y, x, text in sorted(ends):  # labels at the line ends, pushed apart so none sits on another
            y = max([y] + [p + gap for p in placed])
            placed.append(y)
            ax.annotate(text, (x, y), xytext=(8, 0), textcoords="offset points", va="center", color=TEXT,
                        fontsize=10, fontweight="bold")
        first = min(to_vn(p[0][0]) for _, _, p in shown)
        last = max(to_vn(p[-1][0]) for _, _, p in shown)
        ax.set_xlim(first - (last - first) * 0.03, last + (last - first) * 0.16)
        _time_axis(ax, [to_vn(t) for _, _, p in shown for t, _ in p])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: _num(x)))
        ax.set_ylabel("Lượt xem tăng thêm")
        _legend(ax, loc="upper left")
        rate, c, points = shown[0]
        gained, hours = points[-1][1] - points[0][1], (points[-1][0] - points[0][0]).total_seconds() / 3600
        more = (f" Vẽ {len(shown)}/{len(series)} video hot tăng nhanh nhất." if len(series) > len(shown)
                else "")
        note = " ".join((
            "Mỗi đường là một video đã vượt ngưỡng hot, mỗi điểm là một lần đo (bot đo mỗi giờ).",
            "Trục dọc là số lượt xem tăng thêm kể từ lần đo đầu:",
            "đường càng dốc là video càng đang hút người xem,",
            "đường đi ngang là video đã chững lại.",
            "Con số cuối mỗi đường là tốc độ trung bình (lượt xem mỗi giờ)." + more,
        )) + (f"\nNhanh nhất lượt này: {shorten(clean_label(c.shown_title), 40)} "
              f"({_name(c.video.platform)}) — "
              f"+{_num(gained)} lượt xem trong {hours:.0f} giờ, khoảng {_num(rate)} lượt/giờ.")
        return fig, note

    def _scatter(self, run_id, now, candidates):
        usable = [c for c in candidates if c.video.views > 0]
        if len(usable) < MIN_POINTS:
            return None
        n_out = sum(1 for c in usable if c.passed_z)
        fig, ax = frame("Lượt xem và mức vượt kênh",
                        "Mỗi chấm là một video · càng sang phải càng nhiều lượt xem · "
                        "càng lên cao càng vượt xa mức thường của kênh · vòng vàng = video hot", run_id, now)
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
            ax.annotate(shorten(clean_label(c.shown_title), 26), (c.video.views, c.z_score),
                        xytext=(-10 if right_half else 10, -16), textcoords="offset points",
                        ha="right" if right_half else "left", color=TEXT, fontsize=9)
        thresholds = {c.video.platform: c.z_threshold for c in usable if c.z_threshold is not None}
        lines = {t: [p for p, v in thresholds.items() if v == t] for t in set(thresholds.values())}
        for theta, platforms in lines.items():
            who = "" if len(lines) == 1 else " " + ", ".join(_name(p) for p in platforms)
            ax.axhline(theta, color=GOLD, linestyle="--", linewidth=1.4, alpha=0.9)
            ax.annotate(f"ngưỡng hot{who}: {_decimal(theta)}", (1, theta), xycoords=("axes fraction", "data"),
                        xytext=(-4, 5), textcoords="offset points", ha="right", color=TEXT, fontsize=9)
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: _num(x)))
        ax.set_xlabel("Lượt xem (mỗi vạch gấp 10 lần vạch trước)")
        ax.set_ylabel("Mức vượt kênh (z-score)")
        ax.axhline(0, color=GRID, linewidth=1.2)
        _legend(ax, loc="upper left")
        theta = " / ".join(f"{_decimal(t)}" for t in sorted(lines)) or "θ"
        best = max(out, key=lambda c: c.z_score, default=None)
        top = (f"; cao nhất {shorten(clean_label(best.shown_title), 40)} "
               f"(z +{_decimal(round(best.z_score, 1))}, "
               f"{_num(best.video.views)} lượt xem)." if best else ".")
        note = " ".join((
            "Mỗi chấm là một video. Càng sang phải càng nhiều lượt xem; càng lên cao càng vượt xa mức thường",
            "của chính kênh đó. Độ cao là z-score: 0 là video bình thường so với kênh, +2 là vượt rất xa.",
            "Phần lớn video nằm quanh 0 hoặc dưới 0 vì vài video cực hot kéo mức trung bình lên.",
            f"Vạch đứt vàng là ngưỡng hot ({theta}): video trên vạch (vòng vàng) vào danh sách hot.",
            "Đáng chú ý nhất là góc trên bên phải: vừa nhiều lượt xem vừa vượt kênh.",
        )) + f"\nLượt này: {n_out}/{len(usable)} video vượt ngưỡng{top}"
        return fig, note

    def _platform(self, run_id, now, candidates):
        groups = _by_platform(candidates)
        if not groups:
            return None
        counts = [len(v) for v in groups.values()]
        views = [sum(c.video.views for c in v) for v in groups.values()]
        sub = (f"{sum(counts)} video · {_num(sum(views))} lượt xem · vòng trái: số video, "
               "vòng phải: lượt xem")
        fig, base = frame("Tỉ trọng nền tảng", sub, run_id, now)
        base.set_axis_off()  # the donuts have their own axes; the frame's would show a 0–1 grid behind them
        for pos, (title, data, total) in enumerate((("Số video", counts, str(sum(counts))),
                                                     ("Lượt xem", views, _num(sum(views))))):
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
        shares = "; ".join(f"{_name(p)} có {n / sum(counts):.0%} số video và {v / max(sum(views), 1):.0%} "
                           "lượt xem" for p, n, v in zip(groups, counts, views, strict=True))
        note = " ".join((
            "Hai vòng so sánh các nền tảng trong lượt quét này: vòng trái là số video thu được,",
            "vòng phải là tổng lượt xem của chúng. Nền tảng có phần lượt xem lớn hơn phần số video",
            "là nơi mỗi video được xem nhiều hơn.",
        )) + f"\nLượt này: {shares}."
        return fig, note

    def _duration(self, run_id, now, candidates):
        timed = [c for c in candidates if c.video.duration_sec]
        if len(timed) < MIN_POINTS:
            return None
        labels = [b[0] for b in DURATION_BUCKETS]

        def bucket(seconds: int) -> int:
            return next(i for i, (_, hi) in enumerate(DURATION_BUCKETS) if hi is None or seconds < hi)

        groups = _by_platform(timed)
        long_n = sum(1 for c in timed if c.video.duration_sec >= 14400)
        fig, ax = frame("Thời lượng video", f"Số video theo độ dài · {long_n}/{len(timed)} video dài từ "
                        "4 giờ (tuyển tập nhiều tập)", run_id, now)
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
        peak = max(range(len(labels)), key=lambda i: bottoms[i])
        note = " ".join((
            "Mỗi cột là số video thu được trong một khoảng độ dài, mỗi màu là một nền tảng.",
            "Video từ 4 giờ trở lên thường là tuyển tập nhiều tập — loại hợp để lồng tiếng thành phim dài.",
        )) + (f"\nLượt này: {long_n}/{len(timed)} video dài từ 4 giờ; nhiều nhất là nhóm {labels[peak]} "
              f"({bottoms[peak]} video).")
        return fig, note

    def _hours(self, run_id, now, candidates):
        if len(candidates) < MIN_POINTS:
            return None
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap

        groups = _by_platform(candidates)
        grid = np.zeros((len(groups), 24), dtype=int)
        for row, items in enumerate(groups.values()):
            for c in items:
                grid[row, to_vn(c.video.published_at).hour] += 1
        fig, ax = frame("Giờ đăng (giờ Việt Nam)",
                        "Số video được đăng lên vào mỗi giờ · ô càng sáng càng nhiều video", run_id, now)
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
        totals = grid.sum(axis=0)
        busiest = int(totals.argmax())
        note = " ".join((
            "Mỗi ô là số video được đăng lên vào giờ đó (giờ Việt Nam), mỗi hàng là một nền tảng;",
            "ô càng sáng càng nhiều video. Cho biết các kênh cùng thể loại hay đăng vào giờ nào.",
        )) + f"\nLượt này: giờ đăng nhiều nhất là {busiest:02d}h ({int(totals[busiest])} video)."
        return fig, note

    def _keywords(self, run_id, now, candidates):
        tags: dict[str, list[Candidate]] = defaultdict(list)
        for c in candidates:
            if c.video.query_tag:
                tags[c.video.query_tag].append(c)
        rows = sorted(((statistics.median(c.video.views for c in v), tag, v) for tag, v in tags.items()
                       if len(v) >= 2), reverse=True)[:10]
        if len(rows) < 2:
            return None
        fig, ax = frame("Từ khoá hiệu quả nhất",
                        "Lượt xem của video đứng giữa trong số video tìm được bằng mỗi từ khoá · "
                        "n = số video",
                        run_id, now)
        _style(ax, "x")
        ax.set_position([0.24, 0.11, 0.72, 0.64])
        rows.reverse()
        names = [self._tag_name(tag) for _, tag, _ in rows]
        values = [m for m, _, _ in rows]
        colors = gradient_colors(len(rows))[::-1]  # the top bar is teal, the bottom one violet
        bars = ax.barh(names, values, color=colors, height=0.62)
        for bar, (m, _, v) in zip(bars, rows, strict=True):
            ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{_num(m)}  ·  n={len(v)}", va="center", color=TEXT, fontsize=10)
        ax.set_xlim(0, max(values) * 1.22)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: _num(x)))
        ax.set_xlabel("Lượt xem của video đứng giữa (trung vị)")
        m, tag, v = rows[-1]
        note = " ".join((
            "Mỗi thanh là một từ khoá bot dùng để tìm video. Độ dài thanh là lượt xem của video đứng giữa",
            "(trung vị) trong số video tìm được bằng từ khoá đó — không bị một video cực hot làm lệch như số",
            "trung bình; n là số video tìm được. Từ khoá trên cùng mang về video được xem nhiều nhất.",
        )) + f"\nLượt này: đứng đầu là «{self._tag_name(tag)}» — trung vị {_num(m)} lượt xem, n = {len(v)}."
        return fig, note

    @staticmethod
    def _tag_name(tag: str) -> str:
        return shorten(clean_label(tag) or tag, 30)

    def _timeline(self, run_id, now, points):
        if len(points) < 3:
            return None
        xs = [to_vn(p.started_at) for p in points]
        sub = (f"{len(points)} lần chạy mới nhất · mỗi điểm là một lần chạy · khung trên: video thu được, "
               "khung dưới: video hot")
        fig, ax = frame("Các lần chạy gần đây", sub, run_id, now)
        _style(ax)
        ax.set_position([0.07, 0.47, 0.89, 0.28])
        low = fig.add_axes([0.07, 0.11, 0.89, 0.28], sharex=ax)  # one time axis, one scale per panel
        _style(low)
        for side in ("top", "right"):
            low.spines[side].set_visible(False)
        low.tick_params(length=0)
        ax.plot(xs, [p.collected for p in points], color=TEAL, linewidth=2, marker="o", markersize=6,
                markeredgecolor=PANEL, markeredgewidth=1.5)
        ax.set_ylabel("Video thu được")
        ax.set_ylim(0, max(max(p.collected for p in points) * 1.15, 1))
        ax.tick_params(labelbottom=False)
        low.plot(xs, [p.outliers for p in points], color=VIOLET, linewidth=2, marker="o", markersize=6,
                 markeredgecolor=PANEL, markeredgewidth=1.5)
        low.set_ylabel("Video hot")
        low.set_ylim(0, max(max(p.outliers for p in points) * 1.15, 1))
        low.yaxis.get_major_locator().set_params(integer=True)
        _time_axis(low, xs)
        low.margins(x=0.03)
        note = " ".join((
            "Mỗi điểm là một lần bot chạy (chạy mỗi giờ). Khung trên là số video thu được, khung dưới là số",
            "video vượt ngưỡng hot; hai khung chung trục thời gian để thấy lần nào có nhiều video nổi bật.",
        )) + f"\nLần này: {points[-1].collected} video thu được, {points[-1].outliers} video hot."
        return fig, note
