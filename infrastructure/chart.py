"""Charts (docs/01 · L1/L2): a dark "dashboard" look — the theme, fonts, frame and helpers the analysis image
(:mod:`infrastructure.analysis_charts`) is drawn with.

Titles are mostly Chinese now, and matplotlib's default font has no Han glyphs (they render as boxes), so a
CJK font is looked up once; without one (a bare runner) the CJK characters are dropped from labels instead.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from functools import lru_cache

from domain.clock import to_vn

WIDTH_PX, HEIGHT_PX, DPI = 1080, 1080, 100  # a square frame, large enough to read in a phone chat

# Archify "product" style, dark mode: near-black paper, lifted panels, an indigo→violet accent, status hues.
BG, PANEL, TRACK, GRID = "#0c0d10", "#161824", "#1f2230", "#262a31"
TEXT, MUTED = "#f2f3f8", "#8e93a8"
TEAL, ACCENT, VIOLET, MAGENTA, GOLD = "#5cc98d", "#8d80ff", "#a994f5", "#f2806f", "#e9b04f"
GRADIENT = (ACCENT, VIOLET)  # indigo → violet, the product style's signature; the fill of bars
PLATFORM_COLOR = {"youtube": "#f2806f", "bilibili": "#7aa2ff"}
PLATFORM_NAME = {"youtube": "YouTube", "bilibili": "Bilibili"}
NICHE_SCOPE = "Hoạt hình 3D Trung Quốc · Bilibili + YouTube"  # what the hourly digest looks at

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


def stamp(when: datetime) -> str:
    return to_vn(when).strftime("%d/%m/%Y %H:%M")


def frame(title: str, subtitle: str, run_id: str, when: datetime, scope: str | None = None,
          height_px: int = HEIGHT_PX):
    """A themed figure with header and footer (``scope``: what the run looked at; None = the niche), as
    tall as ``height_px`` — the header and footer keep their pixel places; returns ``(fig, ax)`` where ``ax``
    is the content panel."""
    import matplotlib.pyplot as plt

    def y(px: float) -> float:  # a height in pixels from the top → figure fraction
        return 1 - px / height_px

    use_theme()
    fig = plt.figure(figsize=(WIDTH_PX / DPI, height_px / DPI), dpi=DPI)
    fig.text(0.04, y(81), "FlashTrend", color=ACCENT, fontsize=11, fontweight="bold", va="center")
    fig.text(0.04, y(146), title, color=TEXT, fontsize=21, fontweight="bold", va="center")
    fig.text(0.04, y(207), subtitle, color=MUTED, fontsize=11, va="center")
    fig.text(0.96, y(81), f"{stamp(when)} · giờ Việt Nam", color=MUTED, fontsize=10, ha="right", va="center")
    fig.text(0.04, 32 / height_px, run_id, color=MUTED, fontsize=8.5, va="center")
    fig.text(0.96, 32 / height_px, shorten(clean_label(scope or NICHE_SCOPE), 90), color=MUTED, fontsize=8.5,
             ha="right", va="center")
    ax = fig.add_axes([0.07, 119 / height_px, 0.89, 691 / height_px])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    return fig, ax


def to_png(fig, scale: float = 1.0) -> bytes:
    """The figure as PNG bytes, ``scale`` times its pixel size (everything in it scales alike)."""
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=DPI * scale, facecolor=BG)
    finally:
        plt.close(fig)
    return buf.getvalue()
