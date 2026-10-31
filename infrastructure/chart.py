"""Charts (docs/01 · L1/L2): a dark "dashboard" look shared by every image of a run.

The top-ideas chart is drawn by hand in pixel coordinates (rank, title, a progress-style bar, badges); the
analysis charts (:mod:`infrastructure.analysis_charts`) reuse the theme, fonts and helpers below.

Titles are mostly Chinese now, and matplotlib's default font has no Han glyphs (they render as boxes), so a
CJK font is looked up once; without one (a bare runner) the CJK characters are dropped from labels instead.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from functools import lru_cache

from application.ports import ChartImage
from domain.clock import to_vn
from domain.models import Idea

WIDTH_PX, HEIGHT_PX, DPI = 1200, 675, 100

# Power-BI-style dashboard theme: deep navy, slightly lighter panels, and teal → blue → violet accents.
BG, PANEL, TRACK, GRID = "#0a1022", "#131b33", "#212c4a", "#26324f"
TEXT, MUTED = "#eaf0ff", "#8d9cc2"
TEAL, ACCENT, VIOLET, MAGENTA, GOLD = "#2dd4a8", "#4c8dff", "#a77bf3", "#d96cf0", "#f5b841"
GRADIENT = (TEAL, ACCENT, VIOLET)  # the fill of bars, left to right / top to bottom
PLATFORM_COLOR = {"youtube": "#ff6b81", "bilibili": "#35c9ee"}
PLATFORM_NAME = {"youtube": "YouTube", "bilibili": "Bilibili"}

def blend(colors: tuple[str, ...], t: float) -> str:
    """The colour at fraction ``t`` (0..1) along the ``#rrggbb`` stops ``colors``."""
    t = min(max(t, 0.0), 1.0) * (len(colors) - 1)
    i = min(int(t), len(colors) - 2)
    a, b = (tuple(int(colors[k][j:j + 2], 16) for j in (1, 3, 5)) for k in (i, i + 1))
    return "#" + "".join(f"{round(x + (y - x) * (t - i)):02x}" for x, y in zip(a, b, strict=True))


def gradient_colors(n: int, colors: tuple[str, ...] = GRADIENT) -> list[str]:
    """``n`` colours spread over the gradient (the first is ``colors[0]``, the last ``colors[-1]``)."""
    return [blend(colors, i / (n - 1) if n > 1 else 0.0) for i in range(n)]


_CJK_FAMILIES = (
    "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK TC", "Noto Sans CJK HK", "Noto Sans SC",
    "Source Han Sans SC", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei", "Droid Sans Fallback", "PingFang SC",
    "Microsoft YaHei", "SimHei",
)


@lru_cache(maxsize=1)
def cjk_font() -> str | None:
    """The first installed font that can draw Chinese, or None."""
    from matplotlib import font_manager

    installed = {f.name for f in font_manager.fontManager.ttflist}
    return next((f for f in _CJK_FAMILIES if f in installed), None)


def use_theme() -> None:
    """Apply fonts and colours to matplotlib's global style (idempotent)."""
    import matplotlib

    matplotlib.use("Agg")
    families = [f for f in (cjk_font(), "DejaVu Sans") if f]
    matplotlib.rcParams.update({
        "font.family": families,
        "axes.unicode_minus": False,
        "figure.facecolor": BG, "savefig.facecolor": BG,
        "axes.facecolor": PANEL, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
        "xtick.color": MUTED, "ytick.color": MUTED, "text.color": TEXT,
        "grid.color": GRID, "grid.linewidth": 0.8, "axes.grid": False,
    })


_SPACES = re.compile(r"\s+")
_HAN = re.compile(r"[⺀-鿿豈-﫿＀-￯　-〿]")


def clean_label(text: str) -> str:
    """Drop emoji and symbols with no glyph; drop Han too when no CJK font is installed."""
    kept = [c for c in text if ord(c) <= 0xFFFF and unicodedata.category(c) not in ("So", "Cs", "Co", "Cn")]
    out = "".join(kept)
    if cjk_font() is None:
        out = _HAN.sub("", out)
    return _SPACES.sub(" ", out).strip()


def display_width(text: str) -> int:
    """Columns the text takes: a Han/full-width character is two."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def shorten(text: str, limit: int) -> str:
    """Cut to ``limit`` display columns, ending with an ellipsis."""
    if display_width(text) <= limit:
        return text
    out, used = [], 0
    for c in text:
        w = display_width(c)
        if used + w > limit - 1:
            break
        out.append(c)
        used += w
    return "".join(out).rstrip() + "…"


def compact(n: float) -> str:
    """1234567 → ``1.2M``, 45600 → ``45.6K``."""
    n = float(n)
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}".replace(".0", "")
    return f"{n:.0f}"


def age_text(hours: float) -> str:
    return f"{hours:.0f} giờ trước" if hours < 48 else f"{hours / 24:.0f} ngày trước"


def stamp(when: datetime) -> str:
    return to_vn(when).strftime("%d/%m/%Y %H:%M")


def frame(title: str, subtitle: str, run_id: str, when: datetime):
    """A themed figure with header and footer; returns ``(fig, ax)`` where ``ax`` is the content panel."""
    import matplotlib.pyplot as plt

    use_theme()
    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI)
    fig.text(0.04, 0.925, "FlashTrend", color=ACCENT, fontsize=11, fontweight="bold", va="center")
    fig.text(0.04, 0.865, title, color=TEXT, fontsize=21, fontweight="bold", va="center")
    fig.text(0.04, 0.808, subtitle, color=MUTED, fontsize=11, va="center")
    fig.text(0.96, 0.925, f"{stamp(when)} · giờ Việt Nam", color=MUTED, fontsize=10, ha="right", va="center")
    fig.text(0.04, 0.03, run_id, color=MUTED, fontsize=8.5, va="center")
    fig.text(0.96, 0.03, "Hoạt hình 3D Trung Quốc · Bilibili + YouTube", color=MUTED, fontsize=8.5,
             ha="right", va="center")
    ax = fig.add_axes([0.07, 0.11, 0.89, 0.64])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    return fig, ax


def to_png(fig) -> bytes:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=DPI, facecolor=BG)
    finally:
        plt.close(fig)
    return buf.getvalue()


def pill(ax, x: float, y: float, text: str, color: str, width: float = 92, fg: str = "#0b1220") -> None:
    """A rounded badge centred on ``(x, y)`` in pixel coordinates."""
    from matplotlib.patches import FancyBboxPatch

    ax.add_patch(FancyBboxPatch((x - width / 2, y - 11), width, 22, boxstyle="round,pad=0,rounding_size=11",
                                fc=color, ec="none"))
    ax.text(x, y + 0.5, text, color=fg, fontsize=9, fontweight="bold", ha="center", va="center")


def gradient_bar(ax, x: float, y: float, width: float, height: float, full_width: float) -> None:
    """A rounded bar filled with the theme gradient, as much of it as ``width`` out of ``full_width`` shows.

    ``ax`` uses pixel coordinates with y pointing down. The image is clipped to the rounded bar and the
    axes limits are put back, because ``imshow`` would reset them.
    """
    import numpy as np
    from matplotlib.patches import FancyBboxPatch

    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    hexes = gradient_colors(64)
    stops = np.array([[int(c[j:j + 2], 16) for j in (1, 3, 5)] for c in hexes], dtype=float) / 255
    visible = max(2, round(64 * width / full_width))
    strip = stops[:visible][None, :, :]
    shape = FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0,rounding_size=4", fc="none",
                           ec="none")
    ax.add_patch(shape)
    image = ax.imshow(strip, extent=(x, x + width, y + height, y), aspect="auto", interpolation="bilinear",
                      zorder=3)
    image.set_clip_path(shape)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)


class MatplotlibChart:
    """The run's top ideas, ranked in priority order (the niche first), as one shareable card."""

    def render(self, run_id: str, ideas: list[Idea]) -> ChartImage | None:
        if not ideas:
            return None
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, FancyBboxPatch

        use_theme()
        fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, WIDTH_PX)
        ax.set_ylim(HEIGHT_PX, 0)
        ax.axis("off")
        when = ideas[0].candidate.video.captured_at
        ax.text(48, 40, "FlashTrend", color=ACCENT, fontsize=11, fontweight="bold", va="center")
        ax.text(48, 78, "Ý tưởng nổi bật hôm nay", color=TEXT, fontsize=24, fontweight="bold", va="center")
        ax.text(48, 112, "Hoạt hình 3D Trung Quốc ưu tiên · xếp theo điểm viral", color=MUTED, fontsize=11.5,
                va="center")
        ax.text(WIDTH_PX - 48, 40, f"{stamp(when)} · giờ Việt Nam", color=MUTED, fontsize=10, ha="right",
                va="center")

        shown = ideas[:8]
        top, bottom = 140, HEIGHT_PX - 46
        row_h = min(92.0, (bottom - top) / len(shown))
        best = max(i.candidate.viral_score for i in shown) or 1.0
        bar_x, bar_w = 112, 700
        for n, idea in enumerate(shown):
            c, v = idea.candidate, idea.candidate.video
            y = top + n * row_h
            color = PLATFORM_COLOR.get(v.platform, ACCENT)
            ax.add_patch(FancyBboxPatch((32, y + 4), WIDTH_PX - 64, row_h - 8,
                                        boxstyle="round,pad=0,rounding_size=12", fc=PANEL, ec="none"))
            ax.add_patch(Circle((70, y + row_h / 2), 20, fc=color, ec="none"))
            ax.text(70, y + row_h / 2 + 1, str(n + 1), color=BG, fontsize=15, fontweight="bold", ha="center",
                    va="center")
            title = shorten(clean_label(c.shown_title) or v.native_id, 56)
            ax.text(bar_x, y + row_h * 0.30, title, color=TEXT, fontsize=14, fontweight="bold", va="center")
            views, age = compact(v.views), age_text(v.age_hours)
            meta = clean_label(f"{idea.channel_title} · {views} lượt xem · {age} · z {c.z_score:+.1f}")
            ax.text(bar_x, y + row_h * 0.56, shorten(meta, 92), color=MUTED, fontsize=10, va="center")
            by = y + row_h * 0.78
            ax.add_patch(FancyBboxPatch((bar_x, by - 4), bar_w, 8,
                                        boxstyle="round,pad=0,rounding_size=4", fc=TRACK, ec="none"))
            fill = max(10.0, bar_w * c.viral_score / best)
            ax.add_patch(FancyBboxPatch((bar_x, by - 4), fill, 8,
                                        boxstyle="round,pad=0,rounding_size=4", fc="none", ec="none"))
            gradient_bar(ax, bar_x, by - 4, fill, 8, bar_w)
            ax.text(bar_x + bar_w + 14, by, f"{c.viral_score:.1f}", color=TEXT, fontsize=12,
                    fontweight="bold", va="center")
            ax.text(bar_x + bar_w + 14, by - 15, "viral", color=MUTED, fontsize=7.5, va="center")
            pill(ax, WIDTH_PX - 112, y + row_h * 0.34,
                 PLATFORM_NAME.get(v.platform, v.platform).upper(), color)
            if idea.niche:
                pill(ax, WIDTH_PX - 112, y + row_h * 0.68, "NGÁCH 3D", GOLD)
        ax.text(48, HEIGHT_PX - 22, run_id, color=MUTED, fontsize=8.5, va="center")
        ax.text(WIDTH_PX - 48, HEIGHT_PX - 22, "Điểm viral = view × engagement × hiệu suất kênh × độ mới",
                color=MUTED, fontsize=8.5, ha="right", va="center")
        return ChartImage(png=to_png(fig), width=WIDTH_PX, height=HEIGHT_PX)
