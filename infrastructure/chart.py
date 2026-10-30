"""Run chart (docs/01 · L1/L2): the digest's viral scores as one PNG for Telegram / debugging."""
from __future__ import annotations

import io

from application.ports import ChartImage
from domain.clock import to_vn
from domain.models import Idea

WIDTH_PX, HEIGHT_PX, DPI = 1200, 630, 100


class MatplotlibChart:
    def render(self, run_id: str, ideas: list[Idea]) -> ChartImage | None:
        if not ideas:
            return None
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ranked = sorted(ideas, key=lambda i: i.candidate.viral_score)
        labels = [_shorten(i.candidate.video.title, 46) for i in ranked]
        scores = [i.candidate.viral_score for i in ranked]
        fig, ax = plt.subplots(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI)
        try:
            bars = ax.barh(labels, scores, color="#2563eb")
            ax.bar_label(bars, labels=[f"{s:.1f}" for s in scores], padding=4, fontsize=9)
            ax.set_xlabel("viral_score")
            when = to_vn(ranked[-1].candidate.video.captured_at).strftime("%d/%m/%Y %H:%M")
            ax.set_title(f"FlashTrend · {when} (giờ Việt Nam) · {run_id}", fontsize=11)
            ax.margins(x=0.12)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=DPI)
        finally:
            plt.close(fig)
        return ChartImage(png=buf.getvalue(), width=WIDTH_PX, height=HEIGHT_PX)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
