"""Optional debug export (docs/01 · output/): JSON + PNG; Supabase stays the source of truth."""
from __future__ import annotations

import json
from pathlib import Path

from application.digest import RunResult
from domain.clock import now_vn
from infrastructure.timeutil import iso


def result_to_dict(result: RunResult) -> dict:
    cohort = result.stats.cohort
    return {
        "run_id": result.run_id,
        "status": result.status,
        "error": result.error,
        "generated_at": iso(now_vn()),
        "timezone": "Asia/Ho_Chi_Minh (+07:00)",
        "stats": {
            "collected": result.stats.collected,
            "scored": result.stats.scored,
            "outliers": result.stats.outliers,
            "ideas_count": result.stats.ideas_count,
            "duration_ms": result.stats.duration_ms,
            "cohort": None if cohort is None else {
                "n": cohort.n,
                "mu_ratio": cohort.mu_ratio,
                "sigma_ratio": cohort.sigma_ratio,
                "median_engagement": cohort.median_engagement,
                "z_threshold_used": cohort.z_threshold_used,
            },
        },
        "ideas": [
            {
                "video_id": i.video_id,
                "title": i.candidate.video.title,
                "url": i.candidate.video.url,
                "channel_title": i.channel_title,
                "published_at": iso(i.candidate.video.published_at),
                "views": i.candidate.video.views,
                "viral_score": i.candidate.viral_score,
                "z_score": i.candidate.z_score,
                "duplicates_count": i.duplicates_count,
                "novelty_score": i.novelty_score,
                "cluster_id": i.cluster_id,
                "llm": i.llm,
            }
            for i in result.ideas
        ],
    }


def write_output(directory: str | Path, result: RunResult, chart_png: bytes | None) -> list[Path]:
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    path = out / f"{result.run_id}_digest.json"
    path.write_text(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    written.append(path)
    if chart_png:
        png = out / f"{result.run_id}_visual_summary.png"
        png.write_bytes(chart_png)
        written.append(png)
    return written
