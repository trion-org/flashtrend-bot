"""L1 maths (docs/02): relative performance, Z-Score, Bayes engagement, time decay, velocity.

All pure functions over numbers — no I/O, no framework.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

EPSILON = 1e-5


def performance_ratio(views: int, channel_avg_views: float, eps: float = EPSILON) -> float:
    """``views / (channel_avg_views + ε)`` — how many times the channel's usual."""
    return views / (channel_avg_views + eps)


def cohort_mu_sigma(ratios: Sequence[float]) -> tuple[float | None, float | None]:
    """Mean and *sample* σ (n-1) of the cohort; σ is None below two values."""
    if not ratios:
        return None, None
    mu = statistics.fmean(ratios)
    sigma = statistics.stdev(ratios) if len(ratios) >= 2 else None
    return mu, sigma


def z_score(ratio: float, mu: float | None, sigma: float | None) -> float:
    """``(ratio − μ) / σ``; 0 when the cohort has no spread (nothing stands out)."""
    if mu is None or not sigma:
        return 0.0
    return (ratio - mu) / sigma


def choose_z_threshold(
    cohort_n: int, z_threshold: float, relaxed_z_threshold: float, min_cohort_n: int
) -> float:
    """θ, relaxed when the cohort is too small for σ to be trusted (never silently 1.5)."""
    return relaxed_z_threshold if cohort_n < min_cohort_n else z_threshold


def raw_engagement(
    views: int, likes: int, comments: int, like_w: float, comment_w: float
) -> float:
    """``(likes·w1 + comments·w2) / views`` — the unsmoothed engagement used for the prior m."""
    if views <= 0:
        return 0.0
    return (likes * like_w + comments * comment_w) / views


def median_raw_engagement(
    rows: Sequence[tuple[int, int, int]], like_w: float, comment_w: float
) -> float | None:
    """Median raw engagement of the cohort (prior ``m``) over ``(views, likes, comments)``."""
    if not rows:
        return None
    return statistics.median(raw_engagement(v, li, c, like_w, comment_w) for v, li, c in rows)


def niche_match(title: str, description: str, terms: Sequence[str], exclude: Sequence[str] = ()) -> bool:
    """Whether a video belongs to the niche: one of ``terms`` in its title or description, and none of
    ``exclude`` in its title (a description often advertises a course even on a real film).

    Matching is a case-insensitive substring, so it works for Chinese (no word boundaries) as well.
    """
    lowered = title.lower()
    if any(t and t.lower() in lowered for t in exclude):
        return False
    text = f"{lowered}\n{description.lower()}"
    return any(t and t.lower() in text for t in terms)


def engagement(
    views: int,
    likes: int,
    comments: int,
    prior_m: float,
    bayes_c: int,
    like_w: float,
    comment_w: float,
) -> float:
    """Bayes-smoothed ``(likes·w1 + comments·w2 + C·m) / (views + C)``.

    Few-view videos are pulled toward the prior ``m`` instead of jumping to 1.0 on a few likes.
    """
    return (likes * like_w + comments * comment_w + bayes_c * prior_m) / (views + bayes_c)


def time_decay(age_hours: float, decay_lambda: float) -> float:
    """``exp(−λ · age_hours)``; λ = 0.05 → half-life ≈ 13.9 h."""
    return math.exp(-decay_lambda * age_hours)


def half_life_hours(decay_lambda: float) -> float:
    return math.log(2) / decay_lambda


def viral_score(views: int, eng: float, ratio: float, decay: float) -> float:
    """``log1p(views) · engagement · ratio · decay`` — multiplicative, so one weak factor sinks it."""
    return math.log1p(views) * eng * ratio * decay


def velocity(prev_views: int, prev_ts: float, cur_views: int, cur_ts: float) -> float | None:
    """Δviews/Δhours between two snapshots (timestamps in epoch seconds)."""
    dt_h = (cur_ts - prev_ts) / 3600.0
    if dt_h <= 0:
        return None
    return (cur_views - prev_views) / dt_h


def acceleration(prev_velocity: float, prev_ts: float, cur_velocity: float, cur_ts: float) -> float | None:
    """Δvelocity/Δhours (views/h²); needs three snapshots."""
    dt_h = (cur_ts - prev_ts) / 3600.0
    if dt_h <= 0:
        return None
    return (cur_velocity - prev_velocity) / dt_h


def ema(values: Sequence[float], alpha: float = 0.3) -> list[float]:
    """Exponential moving average, seeded with the first value (B5)."""
    out: list[float] = []
    for v in values:
        out.append(v if not out else alpha * v + (1 - alpha) * out[-1])
    return out


def early_flag(vel: float | None, acc: float | None, high_velocity: float | None) -> bool:
    """True only when velocity is high **and** still accelerating (B4).

    "High" = at or above ``high_velocity`` (the cohort's median velocity). Past the peak
    (``acc <= 0``) it stays False even for a very fast video.
    """
    if vel is None or acc is None or high_velocity is None:
        return False
    return vel >= high_velocity and acc > 0
