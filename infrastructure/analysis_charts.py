"""Analysis charts of one run: what a data analyst would look at before choosing an idea — drawn together on
one tall image, one panel per chart, so a reader gets one picture instead of an album of seven.

All of them read the run's scored candidates (the hot videos' earlier snapshots for the growth panel, the last
runs for the timeline) — nothing is fetched here. A panel the data cannot support (no long videos, one run
only…) is left out rather than drawn empty, and the image is as tall as the panels it has. It is the run's
only picture (position 1), rendered as large as a Telegram photo keeps.

Each panel says how to read it under its title, for someone who never read a statistics book; the caption
(shown under the photo in Telegram) gives one line per panel of what this run's data says, and a link to the
docs page that explains every panel at length.
"""
from __future__ import annotations

import statistics
import struct
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

from application.ports import AnalysisImage, RunPoint
from domain.clock import to_vn
from domain.models import Candidate, Idea, PreviousSnapshot
from infrastructure.chart import (
    ACCENT,
    BG,
    GOLD,
    GRID,
    MAGENTA,
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
#: the growth panel: one line per hot-list video (its 10 rows) on one shared scale. Ten hues cannot be told
#: apart, so a line's colour says only how its recent pace compares with its average since upload — the number
#: at the end of the line says which video it is
GROWTH_VIDEOS = 10
FASTER, SLOWER = 1.1, 0.9  # recent pace this many times the average since upload: speeding up / slowing down
LINE_COLOR = "#7aa2ff"  # Archify dark accent-blue: a line that keeps its pace
GROWTH_NAMES_PER_ROW = 5  # the hot list's titles under the growth panel, in rows of this many

DURATION_BUCKETS = (  # (label, upper bound in seconds)
    ("< 1 giờ", 3600), ("1–4 giờ", 14400), ("4–8 giờ", 28800), ("8–24 giờ", 86400), ("> 24 giờ", None),
)

#: the combined image, in pixels: the frame's header above the first panel row, its footer below the last
HEADER_PX, FOOTER_PX = 250, 64
PAGE_LEFT, PAGE_RIGHT = 43, 1037  # the panels' outer edges (the frame's 4 % margins)
COLUMN_GAP, ROW_GAP = 48, 34
PANEL_HEAD = 58  # a panel's title and how-to-read line, above its plot
CAPTION_LIMIT = 1000  # a Telegram photo caption (estfstudio cuts there)
#: the image is drawn on a 1080-wide layout, then rendered up to this many pixels on its long side — the most
#: a Telegram photo keeps — and at most this many times larger, so it stays sharp when zoomed in on a phone
MAX_SIDE_PX, MAX_SCALE = 2560, 2.0
#: the docs page that explains every panel at length
DOCS_URL = "https://trion-org.github.io/flashtrend-bot/04-bang-thu-thap.html"


@dataclass(frozen=True)
class _Panel:
    """One chart of the combined image. ``draw(fig, plot, box)`` draws it — ``plot`` is where its axes go,
    ``box`` the whole panel, both ``[x0, y0, width, height]`` in figure fractions — and returns what this run
    shows, in one line."""

    title: str
    how: str  # one line under the title: what one mark means
    height: int  # px, title and axis labels included
    draw: Callable[..., str]
    wide: bool = False  # a whole row; two narrow panels share one
    inset: tuple[int, int, int] = (64, 16, 58)  # px from the panel's edges to its plot: left, right, bottom


def _rows(panels: list[_Panel]) -> list[list[_Panel]]:
    """Panels into rows, in order: a wide one alone, narrow ones in pairs (a narrow one left alone: wide)."""
    rows: list[list[_Panel]] = []
    pending: _Panel | None = None
    for p in panels:
        if p.wide:
            if pending:
                rows.append([pending])
                pending = None
            rows.append([p])
        elif pending:
            rows.append([pending, p])
            pending = None
        else:
            pending = p
    if pending:
        rows.append([pending])
    return rows


def _caption(findings: list[tuple[str, str]]) -> str:
    """One line per panel — its title and what this run shows — within a Telegram caption's 1000 characters:
    when they do not fit, the longest line is cut first."""
    head, tail = "Bảng phân tích — lượt này cho thấy:", f"Cách đọc từng ô: {DOCS_URL}"
    lines = [f"• {title}: {fact}" for title, fact in findings]
    over = len("\n".join((head, *lines, tail))) - CAPTION_LIMIT
    while over > 0:
        i = max(range(len(lines)), key=lambda k: len(lines[k]))
        cut = shorten(lines[i], max(len(lines[i]) - over, 40))
        over -= len(lines[i]) - len(cut)
        lines[i] = cut
    return "\n".join((head, *lines, tail))


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
    leg = ax.legend(frameon=False, labelcolor=TEXT, **{"fontsize": 9, **kw})
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


def _span(days: float) -> str:
    """How long a stretch lasted: ``3 ngày``, ``5 giờ``."""
    return f"{days:.0f} ngày" if days >= 2 else f"{days * 24:.0f} giờ"


def _pace_color(times: float) -> str:
    """A growth line's colour: its recent pace against its average since upload."""
    return TEAL if times >= FASTER else MAGENTA if times <= SLOWER else LINE_COLOR


def _style(ax, grid: str = "y") -> None:
    ax.set_facecolor(PANEL)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _axes(fig, rect: list[float], grid: str = "y", **kw):
    """A panel's plot, styled like the frame's content axes."""
    ax = fig.add_axes(rect, **kw)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0, labelsize=9)
    _style(ax, grid)
    return ax


def _png_size(png: bytes) -> tuple[int, int]:
    """Width and height, from the PNG header (the size matplotlib rounded the render to)."""
    return struct.unpack(">II", png[16:24])


def _fig_px(fig) -> float:
    return fig.get_figheight() * fig.dpi

class AnalysisCharts:
    def render(
        self,
        run_id: str,
        now: datetime,
        candidates: list[Candidate],
        ideas: list[Idea],
        history: list[RunPoint],
        growth: dict[str, list[PreviousSnapshot]] | None = None,
        listed: list[Candidate] | None = None,
        scope: str | None = None,
    ) -> list[AnalysisImage]:
        """Every chart the data supports, as panels of one image (none: no image); ``history`` = the last
        runs, this one last (the timeline); ``listed`` = the hot list in its order and ``growth`` = their
        earlier snapshots, any order (the growth panel); ``scope`` = what a one-off look looked at, for the
        footer (None: the niche)."""
        panels = [p for p in (
            self._growth(listed or [], growth or {}),
            self._scatter(candidates),
            self._duration(candidates),
            self._hours(candidates),
            self._keywords(candidates),
            self._platform(candidates),
            self._timeline(history),
        ) if p is not None]
        if not panels:
            return []
        rows = _rows(panels)
        heights = [max(p.height for p in row) for row in rows]
        height = HEADER_PX + sum(heights) + ROW_GAP * (len(rows) - 1) + FOOTER_PX
        hot = sum(1 for c in candidates if c.passed_z)
        fig, ax = frame("Bảng phân tích", f"{len(candidates)} video thu được · {hot} video hot · "
                        f"{len(panels)} biểu đồ, mỗi ô một biểu đồ", run_id, now, scope, height)
        ax.remove()
        findings: list[tuple[str, str]] = []
        top = HEADER_PX  # px from the top of the image
        for row, row_px in zip(rows, heights, strict=True):
            width = (PAGE_RIGHT - PAGE_LEFT - COLUMN_GAP * (len(row) - 1)) / len(row)
            for i, panel in enumerate(row):
                left = PAGE_LEFT + i * (width + COLUMN_GAP)
                fig.text(left / WIDTH_PX, 1 - (top + 12) / height, panel.title, color=TEXT, fontsize=13,
                         fontweight="bold", va="center")
                fig.text(left / WIDTH_PX, 1 - (top + 37) / height, panel.how, color=MUTED, fontsize=9,
                         va="center")
                inset_left, inset_right, inset_bottom = panel.inset
                bottom = height - top - row_px  # px from the bottom of the image
                plot = [(left + inset_left) / WIDTH_PX, (bottom + inset_bottom) / height,
                        (width - inset_left - inset_right) / WIDTH_PX,
                        (row_px - PANEL_HEAD - inset_bottom) / height]
                box = [left / WIDTH_PX, bottom / height, width / WIDTH_PX, row_px / height]
                findings.append((panel.title, panel.draw(fig, plot, box)))
            top += row_px + ROW_GAP
        png = to_png(fig, min(MAX_SCALE, MAX_SIDE_PX / height))
        return [AnalysisImage("dashboard", _caption(findings), 1, png, *_png_size(png))]

    # ------------------------------------------------------------------ panels

    def _growth(self, listed, growth):
        """One line per hot-list video the bot measured before, on one scale and one time axis: the views
        it gained since the first time the bot measured it. Bilibili keeps no view history, so a line starts
        at the bot's first measure; a video met for the first time has no line yet. The colour compares the
        measured pace with the video's average pace since upload; the number at a line's end is its rank."""
        shown = [(rank, c) for rank, c in enumerate(listed[:GROWTH_VIDEOS], start=1) if c.video.views > 0]
        lines = []  # (rank, candidate, times, gains, views per day lately, times faster than its average)
        new = []  # ranks met for the first time
        for rank, c in shown:
            seen = {p.captured_at: p.views for p in growth.get(c.video.id, [])
                    if p.captured_at >= c.video.published_at}
            seen[c.video.captured_at] = c.video.views
            points = sorted(seen.items())
            span = (points[-1][0] - points[0][0]).total_seconds() / 86400
            if len(points) < 2 or span * 24 < 1:
                new.append(rank)
                continue
            last_t, last_v = points[-1]
            avg = last_v / max((last_t - c.video.published_at).total_seconds() / 86400, 1 / 24)
            recent = (last_v - points[0][1]) / span
            xs, ys = [to_vn(t) for t, _ in points], [v - points[0][1] for _, v in points]
            lines.append((rank, c, xs, ys, recent, recent / avg if avg else 1.0))
        if not lines:
            return None

        def draw(fig, plot, box) -> str:
            ax = _axes(fig, plot)
            ends = []  # [gained, label height, rank, time] per line
            for rank, _, xs, ys, _, times in lines:
                color = _pace_color(times)
                ax.plot(xs, ys, color=color, linewidth=2, solid_capstyle="round", zorder=2)
                ax.plot(xs[-1:], ys[-1:], marker="o", markersize=7, color=color, markeredgecolor=PANEL,
                        markeredgewidth=2, zorder=3)
                ends.append([ys[-1], ys[-1], rank, xs[-1]])
            low = min(0, *(min(line[3]) for line in lines))  # a recount can take a few views back
            top = max(e[0] for e in ends)
            ends.sort()
            for below, end in zip(ends, ends[1:], strict=False):  # labels 6 % of the scale apart
                end[1] = max(end[1], below[1] + (top - low) * 0.06)
            high = max(top, ends[-1][1])
            ceiling = high + (high - low) * 0.06 or 1
            ax.set_ylim(low, ceiling)
            label_x = 1 + 22 / (plot[2] * WIDTH_PX)  # 22 px right of the plot
            for gained, at, rank, x in ends:  # a hairline back to the line's last point
                ax.annotate(str(rank), (x, gained), xytext=(label_x, (at - low) / (ceiling - low)),
                            textcoords="axes fraction", color=TEXT, fontsize=10, fontweight="bold",
                            va="center", ha="center", annotation_clip=False,
                            arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.8, "shrinkA": 4,
                                        "shrinkB": 5})
            times_all = [x for _, _, xs, _, _, _ in lines for x in xs]
            first, last = min(times_all), max(times_all)
            ax.set_xlim(first, last + (last - first) * 0.012)
            _time_axis(ax, times_all)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: compact(x)))
            ax.set_ylabel("Lượt xem tăng thêm")
            states = ((TEAL, "▲ nhanh hơn trung bình"), (LINE_COLOR, "● giữ nhịp"), (MAGENTA, "▼ chậm lại"))
            handles = [Line2D([], [], color=color, linewidth=2.5, label=label) for color, label in states]
            ax.legend(handles=handles, loc="upper left", frameon=False, labelcolor=TEXT, fontsize=9)
            names = [f"{rank}. {shorten(clean_label(c.shown_title) or c.video.native_id, 22)}"
                     for rank, c, *_ in lines]
            for row in range(-(-len(names) // GROWTH_NAMES_PER_ROW)):  # under the time axis' label
                fig.text(box[0], box[1] + (32 - 19 * row) / _fig_px(fig), "   ".join(
                    names[row * GROWTH_NAMES_PER_ROW:(row + 1) * GROWTH_NAMES_PER_ROW]), color=MUTED,
                    fontsize=8.5, va="bottom")
            rank, c, _, _, pace, times = max(lines, key=lambda line: line[4])
            fact = (f"số {rank}, {shorten(clean_label(c.shown_title), 30)} tăng nhanh nhất — khoảng "
                    f"{_num(pace)} lượt xem mỗi ngày gần đây ({_decimal(round(times, 1))} lần trung bình "
                    f"từ lúc đăng); {len(lines)}/{len(shown)} video đã được bot đo từ trước")
            return fact + (f", số {', '.join(map(str, new))} mới gặp lần đầu" if new else "")

        return _Panel(f"Tăng trưởng lượt xem của {len(lines)} video hot",
                      "Lượt xem tăng thêm kể từ lần bot đo đầu tiên, chung một thang · màu: nhanh hay chậm "
                      "hơn trung bình từ lúc đăng · số cuối đường = thứ tự trong tin nhắn",
                      560, draw, wide=True, inset=(70, 46, 104))

    def _scatter(self, candidates):
        usable = [c for c in candidates if c.video.views > 0]
        if len(usable) < MIN_POINTS:
            return None

        def draw(fig, plot, box) -> str:
            ax = _axes(fig, plot, "both")
            for platform, items in _by_platform(usable).items():
                ax.scatter([c.video.views for c in items], [c.z_score for c in items], s=30, alpha=0.78,
                           color=_color(platform), label=f"{_name(platform)} ({len(items)})", linewidths=0)
            out = [c for c in usable if c.passed_z]
            ax.scatter([c.video.views for c in out], [c.z_score for c in out], s=110, facecolors="none",
                       edgecolors=GOLD, linewidths=1.6, zorder=3)
            middle = statistics.geometric_mean([c.video.views for c in usable])
            for c in sorted(out, key=lambda c: -c.viral_score)[:3]:
                right_half = c.video.views > middle  # right-half labels grow leftwards, inside the plot
                ax.annotate(shorten(clean_label(c.shown_title), 20), (c.video.views, c.z_score),
                            xytext=(-9 if right_half else 9, -14), textcoords="offset points",
                            ha="right" if right_half else "left", color=TEXT, fontsize=8.5)
            thresholds = {c.video.platform: c.z_threshold for c in usable if c.z_threshold is not None}
            lines = {t: [p for p, v in thresholds.items() if v == t] for t in set(thresholds.values())}
            for theta, platforms in lines.items():
                who = "" if len(lines) == 1 else " " + ", ".join(_name(p) for p in platforms)
                ax.axhline(theta, color=GOLD, linestyle="--", linewidth=1.3, alpha=0.9)
                ax.annotate(f"ngưỡng hot{who}: {_decimal(theta)}", (1, theta),
                            xycoords=("axes fraction", "data"), xytext=(-4, 5), textcoords="offset points",
                            ha="right", color=TEXT, fontsize=8.5)
            ax.set_xscale("log")
            ax.margins(y=0.1)  # a hot video at the top keeps its gold ring inside the plot
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: _num(x)))
            ax.set_xlabel("Lượt xem (mỗi vạch gấp 10 lần)")
            ax.set_ylabel("Mức vượt kênh (z-score)")
            ax.axhline(0, color=GRID, linewidth=1.2)
            _legend(ax, loc="upper left")
            theta = " / ".join(f"{_decimal(t)}" for t in sorted(lines)) or "θ"
            best = max(out, key=lambda c: c.z_score, default=None)
            top = (f"; cao nhất {shorten(clean_label(best.shown_title), 30)} "
                   f"(z +{_decimal(round(best.z_score, 1))}, {_num(best.video.views)} lượt xem)"
                   if best else "")
            return f"{len(out)}/{len(usable)} video vượt ngưỡng hot {theta}{top}"

        return _Panel("Lượt xem và mức vượt kênh",
                      "Chấm = video · phải: nhiều lượt xem · cao: vượt xa kênh · vòng vàng: hot", 450, draw,
                      inset=(70, 14, 58))

    def _duration(self, candidates):
        timed = [c for c in candidates if c.video.duration_sec]
        if len(timed) < MIN_POINTS:
            return None
        labels = [b[0] for b in DURATION_BUCKETS]
        long_n = sum(1 for c in timed if c.video.duration_sec >= 14400)

        def bucket(seconds: int) -> int:
            return next(i for i, (_, hi) in enumerate(DURATION_BUCKETS) if hi is None or seconds < hi)

        def draw(fig, plot, box) -> str:
            ax = _axes(fig, plot)
            bottoms = [0] * len(labels)
            for platform, items in _by_platform(timed).items():
                counts = [0] * len(labels)
                for c in items:
                    counts[bucket(c.video.duration_sec)] += 1
                ax.bar(labels, counts, bottom=bottoms, color=_color(platform), label=_name(platform),
                       width=0.62)
                bottoms = [b + n for b, n in zip(bottoms, counts, strict=True)]
            for x, total in enumerate(bottoms):
                if total:
                    ax.text(x, total + max(bottoms) * 0.02, str(total), ha="center", color=TEXT, fontsize=10,
                            fontweight="bold")
            ax.set_ylim(0, max(bottoms) * 1.15)
            ax.set_ylabel("Số video")
            _legend(ax, loc="upper right")
            peak = max(range(len(labels)), key=lambda i: bottoms[i])
            return (f"{long_n}/{len(timed)} video dài từ 4 giờ; nhiều nhất là nhóm {labels[peak]} "
                    f"({bottoms[peak]} video)")

        return _Panel("Thời lượng video", f"Số video theo độ dài · {long_n}/{len(timed)} video dài từ 4 giờ "
                      "(tuyển tập)", 450, draw, inset=(56, 14, 40))

    def _hours(self, candidates):
        if len(candidates) < MIN_POINTS:
            return None
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap

        groups = _by_platform(candidates)
        grid = np.zeros((len(groups), 24), dtype=int)
        for row, items in enumerate(groups.values()):
            for c in items:
                grid[row, to_vn(c.video.published_at).hour] += 1

        def draw(fig, plot, box) -> str:
            ax = _axes(fig, plot)
            ax.grid(False)
            heat = LinearSegmentedColormap.from_list("t", [PANEL, "#2c3a9e", VIOLET, TEAL])
            ax.imshow(grid, aspect="auto", cmap=heat)
            ax.set_xticks(range(24), [f"{h:02d}" for h in range(24)], fontsize=8.5)
            ax.set_yticks(range(len(groups)), [_name(p) for p in groups], fontsize=10)
            peak = grid.max() or 1
            for (r, h), n in np.ndenumerate(grid):
                if n:
                    ax.text(h, r, str(n), ha="center", va="center", fontsize=8.5,
                            color=BG if n > peak * 0.55 else TEXT)
            ax.set_xlabel("Giờ trong ngày")
            for side in ax.spines.values():
                side.set_visible(False)
            totals = grid.sum(axis=0)
            busiest = int(totals.argmax())
            return f"giờ đăng nhiều nhất là {busiest:02d}h ({int(totals[busiest])} video)"

        return _Panel("Giờ đăng (giờ Việt Nam)",
                      "Số video được đăng lên vào mỗi giờ · mỗi hàng một nền tảng · "
                      "ô càng sáng càng nhiều video",
                      150 + 40 * len(groups), draw, wide=True, inset=(84, 14, 50))

    def _keywords(self, candidates):
        tags: dict[str, list[Candidate]] = defaultdict(list)
        for c in candidates:
            if c.video.query_tag:
                tags[c.video.query_tag].append(c)
        rows = sorted(((statistics.median(c.video.views for c in v), tag, v) for tag, v in tags.items()
                       if len(v) >= 2), reverse=True)[:10]
        if len(rows) < 2:
            return None

        def draw(fig, plot, box) -> str:
            ax = _axes(fig, plot, "x")
            shown = rows[::-1]  # the best at the top
            names = [self._tag_name(tag) for _, tag, _ in shown]
            values = [m for m, _, _ in shown]
            colors = gradient_colors(len(shown))[::-1]  # the top bar indigo, fading to violet down the list
            bars = ax.barh(names, values, color=colors, height=0.62)
            for bar, (m, _, v) in zip(bars, shown, strict=True):
                ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                        f"{_num(m)}  ·  n={len(v)}", va="center", color=TEXT, fontsize=9)
            ax.tick_params(axis="y", labelsize=9.5)
            ax.set_xlim(0, max(values) * 1.22)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: _num(x)))
            ax.set_xlabel("Lượt xem của video đứng giữa (trung vị)")
            m, tag, v = rows[0]
            return f"đứng đầu là «{self._tag_name(tag)}» — trung vị {_num(m)} lượt xem, n = {len(v)}"

        return _Panel("Từ khoá hiệu quả nhất",
                      "Lượt xem của video đứng giữa (trung vị) trong số video tìm được bằng mỗi từ khoá · "
                      "n = số video", 120 + 32 * len(rows), draw, wide=True, inset=(210, 14, 56))

    @staticmethod
    def _tag_name(tag: str) -> str:
        return shorten(clean_label(tag) or tag, 30)

    def _platform(self, candidates):
        groups = _by_platform(candidates)
        if len(groups) < 2:  # one platform (a Bilibili-only look) is all of everything: nothing to compare
            return None
        counts = [len(v) for v in groups.values()]
        views = [sum(c.video.views for c in v) for v in groups.values()]

        def draw(fig, plot, box) -> str:
            from matplotlib.patches import Patch

            x0, y0, w, h = plot
            for pos, (title, data, total) in enumerate((("Số video", counts, str(sum(counts))),
                                                         ("Lượt xem", views, _num(sum(views))))):
                ax = fig.add_axes([x0 + pos * w / 2, y0, w / 2, h])
                ax.set_axis_off()
                ax.pie(data, colors=[_color(p) for p in groups], startangle=90, counterclock=False,
                       wedgeprops={"width": 0.26, "edgecolor": BG, "linewidth": 3})
                ax.text(0, 0.06, total, ha="center", va="center", fontsize=17, fontweight="bold", color=TEXT)
                ax.text(0, -0.22, title, ha="center", va="center", fontsize=9.5, color=MUTED)
                share = "  ·  ".join(f"{_name(p)} {v / sum(data):.0%}"
                                     for p, v in zip(groups, data, strict=True))
                ax.set_title(share, color=TEXT, fontsize=9.5, pad=2)
            fig.legend(handles=[Patch(color=_color(p), label=_name(p)) for p in groups], loc="lower center",
                       ncol=len(groups), frameon=False, labelcolor=TEXT, fontsize=9,
                       bbox_to_anchor=(box[0] + box[2] / 2, box[1]))
            return "; ".join(f"{_name(p)} có {n / sum(counts):.0%} số video và {v / max(sum(views), 1):.0%} "
                             "lượt xem" for p, n, v in zip(groups, counts, views, strict=True))

        return _Panel("Tỉ trọng nền tảng", f"{sum(counts)} video · {_num(sum(views))} lượt xem · "
                      "vòng trái: số video, vòng phải: lượt xem", 450, draw, inset=(8, 8, 40))

    def _timeline(self, points):
        if len(points) < 3:
            return None
        xs = [to_vn(p.started_at) for p in points]

        def draw(fig, plot, box) -> str:
            x0, y0, w, h = plot
            gap = 18 / _fig_px(fig)  # px between the two plots
            up = _axes(fig, [x0, y0 + (h + gap) / 2, w, (h - gap) / 2])
            low = _axes(fig, [x0, y0, w, (h - gap) / 2], sharex=up)  # one time axis, one scale per plot
            up.plot(xs, [p.collected for p in points], color=TEAL, linewidth=2, marker="o", markersize=5,
                    markeredgecolor=PANEL, markeredgewidth=1.5)
            up.set_ylabel("Thu được")
            up.set_ylim(0, max(max(p.collected for p in points) * 1.15, 1))
            up.tick_params(labelbottom=False)
            low.plot(xs, [p.outliers for p in points], color=VIOLET, linewidth=2, marker="o", markersize=5,
                     markeredgecolor=PANEL, markeredgewidth=1.5)
            low.set_ylabel("Video hot")
            low.set_ylim(0, max(max(p.outliers for p in points) * 1.15, 1))
            low.yaxis.get_major_locator().set_params(integer=True)
            _time_axis(low, xs)
            low.margins(x=0.03)
            return f"lần này {points[-1].collected} video thu được, {points[-1].outliers} video hot"

        return _Panel("Các lần chạy gần đây", f"{len(points)} lần chạy mới nhất · trên: video thu được · "
                      "dưới: video hot", 450, draw, inset=(64, 14, 58))
